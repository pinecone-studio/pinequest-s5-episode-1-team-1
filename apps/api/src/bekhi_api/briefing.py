"""The day at a glance (daily_briefing): a greeting for the time of day, today's weather, and the
to-dos due today or overdue. The phone adds what it has scheduled today: the planner calls
list_reminders in the same turn, and compose.py keeps only today's items from it."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx

from . import backend_tools, todos
from .models import ActionResult

MAX_TITLES = 5
MAX_CARD_TODOS = 8


def greeting(now: datetime) -> str:
    if 4 <= now.hour < 11:
        return "Өглөөний мэнд!"
    if 11 <= now.hour < 17:
        return "Өдрийн мэнд!"
    if 17 <= now.hour < 23:
        return "Оройн мэнд!"
    return "Сайн байна уу!"


def _due(item: dict[str, Any]) -> date | None:
    return date.fromisoformat(item["due_at"][:10]) if item.get("due_at") else None


def _titles(items: list[dict[str, Any]]) -> str:
    names = [str(i["title"]) for i in items[:MAX_TITLES]]
    more = f" гэх мэт {len(items)} зүйл" if len(items) > MAX_TITLES else ""
    return ", ".join(names) + more


def todo_sentence(items: list[dict[str, Any]], today: date) -> str:
    """"Өнөөдөр хийх 2 зүйл байна: ..." — what is due today, overdue, and how much else is open."""
    open_items = [i for i in items if not i["done"]]
    if not open_items:
        return "Хийх зүйлийн жагсаалт хоосон байна."
    due_today = [i for i in open_items if _due(i) == today]
    overdue = [i for i in open_items if (d := _due(i)) is not None and d < today]
    rest = len(open_items) - len(due_today) - len(overdue)
    parts = []
    if due_today:
        parts.append(f"Өнөөдөр хийх {len(due_today)} зүйл байна: {_titles(due_today)}.")
    if overdue:
        parts.append(f"Хугацаа хэтэрсэн {len(overdue)} зүйл бий: {_titles(overdue)}.")
    if not parts:
        parts.append(f"Жагсаалтад {len(open_items)} зүйл байна: {_titles(open_items)}.")
    elif rest:
        parts.append(f"Жагсаалтад бас {rest} зүйл бий.")
    return " ".join(parts)


def card_todos(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The open to-dos for the app's card, those with a due time first, soonest first."""
    open_items = [i for i in items if not i["done"]]
    open_items.sort(key=lambda i: (i.get("due_at") is None, i.get("due_at") or ""))
    return [{"title": i["title"], "due_at": i.get("due_at"), "done": False} for i in open_items[:MAX_CARD_TODOS]]


async def daily_briefing(action_id: str, args: dict[str, Any], client_now: datetime, http: httpx.AsyncClient,
                         store: todos.TodoStore, account: str | None) -> ActionResult:
    parts = [greeting(client_now)]
    # weather and todos: what the app shows as cards under the spoken summary.
    data: dict[str, Any] = {}
    weather = await backend_tools.get_weather(action_id, {"location_name": args.get("location_name")}, client_now, http)
    if weather.status == "succeeded" and weather.data:
        parts.append(str(weather.data["summary_mn"]))
        data["weather"] = {k: v for k, v in weather.data.items() if k != "summary_mn"}
    else:
        parts.append("Цаг агаарын мэдээг одоо авч чадсангүй.")
    try:
        items = await store.items(account)
        parts.append(todo_sentence(items, client_now.date()))
        data["todos"] = card_todos(items)
    except httpx.HTTPError:
        parts.append("Хийх зүйлийн жагсаалтыг одоо харж чадсангүй.")
    return ActionResult(
        action_id=action_id, tool="daily_briefing", status="succeeded", executed_via="backend", error_code=None,
        data={**data, "summary_mn": " ".join(parts)},
    )
