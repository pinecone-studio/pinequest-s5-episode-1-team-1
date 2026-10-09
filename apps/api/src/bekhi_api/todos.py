"""The to-do list (add_todo, list_todos, complete_todo, delete_todo), one per account: the devices
linked with one sync code (sync.py) share it, and nobody else sees it.

Supabase holds the lists when SUPABASE_URL is set (supabase/migrations); otherwise a JSON file per
account on the machine running the API. A request without a sync code (an app from before
accounts) uses the single list the API always kept, in TODO_FILE."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx

from .compose import format_when_mn
from .config import API_ROOT
from .models import ActionResult

MAX_TODOS = 500
LIST_LIMIT = 8

FILTER_MN = {
    "open": "хийх",
    "today": "өнөөдрийн",
    "tomorrow": "маргаашийн",
    "week": "энэ долоо хоногийн",
    "overdue": "хугацаа хэтэрсэн",
    "done": "хийгдсэн",
    "all": "бүх",
}


class TodoStore(Protocol):
    """Items are {id, title, due_at (ISO-8601 as the planner wrote it, or None), done, created_at}.
    `account` is the sync account (sync.account_key), or None for the list without one."""

    async def items(self, account: str | None) -> list[dict[str, Any]]: ...
    async def add(self, account: str | None, item: dict[str, Any]) -> None: ...
    async def mark_done(self, account: str | None, ids: list[str]) -> None: ...
    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        """Deletes these items, or all of them when ids is None."""
        ...


class FileTodoStore:
    """A JSON file per account next to TODO_FILE (default apps/api/data/todos.json)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _path(account: str | None) -> Path:
        legacy = Path(os.getenv("TODO_FILE") or API_ROOT / "data" / "todos.json")
        return legacy if account is None else legacy.with_name(f"todos-{account}.json")

    def _load(self, account: str | None) -> list[dict[str, Any]]:
        try:
            return json.loads(self._path(account).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return []

    def _save(self, account: str | None, items: list[dict[str, Any]]) -> None:
        p = self._path(account)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    async def items(self, account: str | None) -> list[dict[str, Any]]:
        with self._lock:
            return self._load(account)

    async def add(self, account: str | None, item: dict[str, Any]) -> None:
        with self._lock:
            self._save(account, [*self._load(account), item])

    async def mark_done(self, account: str | None, ids: list[str]) -> None:
        with self._lock:
            self._save(account, [{**i, "done": True} if i["id"] in ids else i for i in self._load(account)])

    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        with self._lock:
            self._save(account, [] if ids is None else [i for i in self._load(account) if i["id"] not in ids])


class SupabaseTodoStore:
    """The `todos` table through PostgREST with the service role key (server only; RLS has no
    policies). The list without an account stays in the file, as before."""

    def __init__(self, url: str, service_key: str, http: httpx.AsyncClient, legacy: FileTodoStore) -> None:
        self._rest = url.rstrip("/") + "/rest/v1/todos"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._http = http
        self._legacy = legacy

    async def _call(self, method: str, params: dict[str, str], json: Any = None) -> Any:
        r = await self._http.request(
            method, self._rest, params=params, json=json, headers={**self._headers, "Prefer": "return=minimal"}
        )
        r.raise_for_status()
        return r.json() if r.content else None

    async def items(self, account: str | None) -> list[dict[str, Any]]:
        if account is None:
            return await self._legacy.items(None)
        rows = await self._call("GET", {
            "select": "id,title,due_at,done,created_at",
            "account_hash": f"eq.{account}",
            "order": "created_at.asc",
            "limit": str(MAX_TODOS),
        })
        return list(rows or [])

    async def add(self, account: str | None, item: dict[str, Any]) -> None:
        if account is None:
            return await self._legacy.add(None, item)
        await self._call("POST", {}, {**item, "account_hash": account})

    async def mark_done(self, account: str | None, ids: list[str]) -> None:
        if account is None:
            return await self._legacy.mark_done(None, ids)
        await self._call("PATCH", {"account_hash": f"eq.{account}", "id": f"in.({','.join(ids)})"}, {"done": True})

    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        if account is None:
            return await self._legacy.delete(None, ids)
        params = {"account_hash": f"eq.{account}"}
        if ids is not None:
            params["id"] = f"in.({','.join(ids)})"
        await self._call("DELETE", params)


def make_store(supabase_url: str | None, service_key: str | None, http: httpx.AsyncClient) -> TodoStore:
    if supabase_url and service_key:
        return SupabaseTodoStore(supabase_url, service_key, http, FileTodoStore())
    return FileTodoStore()


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", "", s.casefold())


def _matches(item: dict[str, Any], query: str) -> bool:
    q, t = _norm(query), _norm(item["title"])
    return bool(q) and (q in t or t in q)


def _ok(action_id: str, tool: str, summary: str, **data: Any) -> ActionResult:
    return ActionResult(
        action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None,
        data={**data, "summary_mn": summary},
    )


def _fail(action_id: str, tool: str, code: str, count: int | None = None) -> ActionResult:
    return ActionResult(
        action_id=action_id, tool=tool, status="failed", executed_via="backend", error_code=code, match_count=count, data=None
    )


def _due_day(item: dict[str, Any]) -> date | None:
    return date.fromisoformat(item["due_at"][:10]) if item.get("due_at") else None


def _in_filter(item: dict[str, Any], flt: str, today: date) -> bool:
    day = _due_day(item)
    if flt == "done":
        return item["done"]
    if flt == "all":
        return True
    if item["done"]:
        return False
    return {
        "open": True,
        "today": day == today,
        "tomorrow": day == today + timedelta(days=1),
        "week": day is not None and today <= day <= today + timedelta(days=6),
        "overdue": day is not None and day < today,
    }[flt]


async def add_todo(action_id: str, args: dict[str, Any], client_now: datetime, store: TodoStore,
                   account: str | None) -> ActionResult:
    if len(await store.items(account)) >= MAX_TODOS:
        return _fail(action_id, "add_todo", "TODO_FULL")
    title, due = str(args["title"]).strip(), args.get("due_at")
    await store.add(account, {"id": str(uuid4()), "title": title, "due_at": due, "done": False,
                              "created_at": client_now.isoformat()})
    summary = f"За, '{title}' гэж жагсаалтад нэмлээ."
    if due:
        summary += f" Хугацаа нь {format_when_mn(due, client_now.isoformat())}."
    return _ok(action_id, "add_todo", summary, title=title)


async def list_todos(action_id: str, args: dict[str, Any], client_now: datetime, store: TodoStore,
                     account: str | None) -> ActionResult:
    flt = args.get("filter", "open")
    today = client_now.date()
    items = [i for i in await store.items(account) if _in_filter(i, flt, today)]
    items.sort(key=lambda i: (i["due_at"] is None, i["due_at"] or "", i["created_at"]))
    label = FILTER_MN[flt]
    if not items:
        return _ok(action_id, "list_todos", f"{label.capitalize()} зүйл алга байна.", items=[])
    now_iso = client_now.isoformat()
    parts = [f"{i['title']} ({format_when_mn(i['due_at'], now_iso)})" if i.get("due_at") else i["title"] for i in items[:LIST_LIMIT]]
    more = f", бас {len(items) - LIST_LIMIT} зүйл" if len(items) > LIST_LIMIT else ""
    summary = f"{label.capitalize()} {len(items)} зүйл байна: " + ", ".join(parts) + more + "."
    return _ok(action_id, "list_todos", summary, items=[{"title": i["title"], "due_at": i.get("due_at"), "done": i["done"]} for i in items])


async def complete_todo(action_id: str, args: dict[str, Any], store: TodoStore, account: str | None) -> ActionResult:
    found = [i for i in await store.items(account) if not i["done"] and _matches(i, args["query"])]
    if not found:
        return _fail(action_id, "complete_todo", "TODO_NOT_FOUND")
    if len(found) > 1:
        return _fail(action_id, "complete_todo", "TODO_AMBIGUOUS", len(found))
    await store.mark_done(account, [found[0]["id"]])
    return _ok(action_id, "complete_todo", f"За, '{found[0]['title']}' хийгдсэн гэж тэмдэглэлээ.", title=found[0]["title"])


async def delete_todo(action_id: str, args: dict[str, Any], store: TodoStore, account: str | None) -> ActionResult:
    items = await store.items(account)
    if args.get("all"):
        gone = items
    elif args.get("query"):
        gone = [i for i in items if _matches(i, args["query"])]
    else:
        return _fail(action_id, "delete_todo", "TODO_AMBIGUOUS", len(items))
    if not gone:
        return _fail(action_id, "delete_todo", "TODO_NOT_FOUND")
    if len(gone) > 1 and not args.get("all"):
        return _fail(action_id, "delete_todo", "TODO_AMBIGUOUS", len(gone))
    await store.delete(account, None if args.get("all") else [i["id"] for i in gone])
    summary = "За, жагсаалтыг бүгдийг нь цэвэрлэлээ." if args.get("all") else f"За, '{gone[0]['title']}' -ийг жагсаалтаас устгалаа."
    return _ok(action_id, "delete_todo", summary)
