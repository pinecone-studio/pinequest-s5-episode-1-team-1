"""What the user asked BEKHI to remember (remember, forget): short facts per account, given to the
planner with every request, so "эхнэр рүүгээ залга" can call the wife it was told about.

One list per account (the sync code, as todos.py). Supabase holds them when SUPABASE_URL is set
(supabase/migrations); otherwise a JSON file per account next to MEMORY_FILE. Facts are personal:
they are never logged."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx

from .config import API_ROOT
from .models import ActionResult

MAX_FACTS = 50


class FactStore(Protocol):
    """Facts are {id, text, created_at}; `account` is the sync account, or None without a code."""

    async def items(self, account: str | None) -> list[dict[str, Any]]: ...
    async def add(self, account: str | None, item: dict[str, Any]) -> None: ...
    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        """Deletes these facts, or all of them when ids is None."""
        ...


class FileFactStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _path(account: str | None) -> Path:
        base = Path(os.getenv("MEMORY_FILE") or API_ROOT / "data" / "memory.json")
        return base if account is None else base.with_name(f"memory-{account}.json")

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

    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        with self._lock:
            self._save(account, [] if ids is None else [i for i in self._load(account) if i["id"] not in ids])


class SupabaseFactStore:
    """The `memories` table through PostgREST with the service role key (server only)."""

    def __init__(self, url: str, service_key: str, http: httpx.AsyncClient, legacy: FileFactStore) -> None:
        self._rest = url.rstrip("/") + "/rest/v1/memories"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}", "Prefer": "return=minimal"}
        self._http = http
        self._legacy = legacy

    async def _call(self, method: str, params: dict[str, str], json: Any = None) -> Any:
        r = await self._http.request(method, self._rest, params=params, json=json, headers=self._headers)
        r.raise_for_status()
        return r.json() if r.content else None

    async def items(self, account: str | None) -> list[dict[str, Any]]:
        if account is None:
            return await self._legacy.items(None)
        rows = await self._call("GET", {"select": "id,text,created_at", "account_hash": f"eq.{account}",
                                        "order": "created_at.asc", "limit": str(MAX_FACTS)})
        return list(rows or [])

    async def add(self, account: str | None, item: dict[str, Any]) -> None:
        if account is None:
            return await self._legacy.add(None, item)
        await self._call("POST", {}, {**item, "account_hash": account})

    async def delete(self, account: str | None, ids: list[str] | None) -> None:
        if account is None:
            return await self._legacy.delete(None, ids)
        params = {"account_hash": f"eq.{account}"}
        if ids is not None:
            params["id"] = f"in.({','.join(ids)})"
        await self._call("DELETE", params)


def make_store(supabase_url: str | None, service_key: str | None, http: httpx.AsyncClient) -> FactStore:
    if supabase_url and service_key:
        return SupabaseFactStore(supabase_url, service_key, http, FileFactStore())
    return FileFactStore()


def _norm(s: str) -> str:
    return re.sub(r"[^\w]+", "", s.casefold())


def _result(action_id: str, tool: str, summary: str | None, code: str | None = None) -> ActionResult:
    if code:
        return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend", error_code=code, data=None)
    return ActionResult(action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None,
                        data={"summary_mn": summary})


async def remember(action_id: str, args: dict[str, Any], client_now: datetime, store: FactStore,
                   account: str | None) -> ActionResult:
    text = str(args["fact"]).strip()
    facts = await store.items(account)
    if any(_norm(f["text"]) == _norm(text) for f in facts):
        return _result(action_id, "remember", "За, үүнийг санаж байгаа.")
    if len(facts) >= MAX_FACTS:
        return _result(action_id, "remember", None, "MEMORY_FULL")
    await store.add(account, {"id": str(uuid4()), "text": text, "created_at": client_now.isoformat()})
    return _result(action_id, "remember", "За, санаж авлаа.")


async def forget(action_id: str, args: dict[str, Any], store: FactStore, account: str | None) -> ActionResult:
    if args.get("all"):
        await store.delete(account, None)
        return _result(action_id, "forget", "За, санасан бүх зүйлээ мартлаа.")
    # Every word of the query, by its first letters: Mongolian endings vary ("эхнэр", "эхнэрийн").
    stems = [w[:4] for w in re.findall(r"\w+", str(args.get("query") or "").casefold())]
    gone = [f for f in await store.items(account) if stems and all(s in _norm(f["text"]) for s in stems)]
    if not gone:
        return _result(action_id, "forget", None, "MEMORY_NOT_FOUND")
    await store.delete(account, [f["id"] for f in gone])
    return _result(action_id, "forget", "За, мартлаа.")


async def facts_for(store: FactStore, account: str | None) -> list[str]:
    """The facts for the planner's prompt; none when the store cannot be read (the turn goes on)."""
    try:
        return [str(f["text"]) for f in await store.items(account)][:MAX_FACTS]
    except httpx.HTTPError:
        return []
