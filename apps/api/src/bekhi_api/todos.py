"""The to-do list (add_todo, list_todos, complete_todo, delete_todo): a JSON file on the machine
running the API, so the same list shows on the phone and in the browser. Single user."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .compose import format_when_mn
from .config import API_ROOT
from .models import ActionResult

MAX_TODOS = 500
LIST_LIMIT = 8
_lock = threading.Lock()

FILTER_MN = {
    "open": "хийх",
    "today": "өнөөдрийн",
    "tomorrow": "маргаашийн",
    "week": "энэ долоо хоногийн",
    "overdue": "хугацаа хэтэрсэн",
    "done": "хийгдсэн",
    "all": "бүх",
}


def _path() -> Path:
    return Path(os.getenv("TODO_FILE") or API_ROOT / "data" / "todos.json")


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _save(items: list[dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


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


def add_todo(action_id: str, args: dict[str, Any], client_now: datetime) -> ActionResult:
    with _lock:
        items = _load()
        if len(items) >= MAX_TODOS:
            return _fail(action_id, "add_todo", "TODO_FULL")
        title, due = str(args["title"]).strip(), args.get("due_at")
        items.append({"id": uuid4().hex[:8], "title": title, "due_at": due, "done": False, "created_at": client_now.isoformat()})
        _save(items)
    summary = f"За, '{title}' гэж жагсаалтад нэмлээ."
    if due:
        summary += f" Хугацаа нь {format_when_mn(due, client_now.isoformat())}."
    return _ok(action_id, "add_todo", summary, title=title)


def list_todos(action_id: str, args: dict[str, Any], client_now: datetime) -> ActionResult:
    flt = args.get("filter", "open")
    today = client_now.date()
    with _lock:
        items = [i for i in _load() if _in_filter(i, flt, today)]
    items.sort(key=lambda i: (i["due_at"] is None, i["due_at"] or "", i["created_at"]))
    label = FILTER_MN[flt]
    if not items:
        return _ok(action_id, "list_todos", f"{label.capitalize()} зүйл алга байна.", items=[])
    now_iso = client_now.isoformat()
    parts = [f"{i['title']} ({format_when_mn(i['due_at'], now_iso)})" if i.get("due_at") else i["title"] for i in items[:LIST_LIMIT]]
    more = f", бас {len(items) - LIST_LIMIT} зүйл" if len(items) > LIST_LIMIT else ""
    summary = f"{label.capitalize()} {len(items)} зүйл байна: " + ", ".join(parts) + more + "."
    return _ok(action_id, "list_todos", summary, items=[{"title": i["title"], "due_at": i.get("due_at"), "done": i["done"]} for i in items])


def complete_todo(action_id: str, args: dict[str, Any]) -> ActionResult:
    with _lock:
        items = _load()
        found = [i for i in items if not i["done"] and _matches(i, args["query"])]
        if not found:
            return _fail(action_id, "complete_todo", "TODO_NOT_FOUND")
        if len(found) > 1:
            return _fail(action_id, "complete_todo", "TODO_AMBIGUOUS", len(found))
        found[0]["done"] = True
        _save(items)
    return _ok(action_id, "complete_todo", f"За, '{found[0]['title']}' хийгдсэн гэж тэмдэглэлээ.", title=found[0]["title"])


def delete_todo(action_id: str, args: dict[str, Any]) -> ActionResult:
    with _lock:
        items = _load()
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
        _save([i for i in items if i not in gone])
    summary = "За, жагсаалтыг бүгдийг нь цэвэрлэлээ." if args.get("all") else f"За, '{gone[0]['title']}' -ийг жагсаалтаас устгалаа."
    return _ok(action_id, "delete_todo", summary)
