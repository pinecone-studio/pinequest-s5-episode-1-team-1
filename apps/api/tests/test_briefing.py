from datetime import date, datetime

import pytest

from bekhi_api import briefing

from .conftest import context

TODAY = date(2026, 10, 6)


@pytest.fixture(autouse=True)
def todo_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TODO_FILE", str(tmp_path / "todos.json"))


def item(title, due=None, done=False):
    return {"id": title, "title": title, "due_at": due, "done": done, "created_at": "2026-10-01T09:00:00+08:00"}


def test_greeting_follows_the_time_of_day():
    at = lambda h: briefing.greeting(datetime(2026, 10, 6, h, 0))  # noqa: E731
    assert [at(7), at(13), at(20), at(2)] == ["Өглөөний мэнд!", "Өдрийн мэнд!", "Оройн мэнд!", "Сайн байна уу!"]


def test_todos_due_today_and_overdue_come_first():
    items = [
        item("Тайлан илгээх", "2026-10-06T23:59:00+08:00"),
        item("Ном буцаах", "2026-10-04T12:00:00+08:00"),
        item("Сүү авах"),
        item("Хуучин ажил", "2026-10-06T10:00:00+08:00", done=True),
    ]
    assert briefing.todo_sentence(items, TODAY) == (
        "Өнөөдөр хийх 1 зүйл байна: Тайлан илгээх. Хугацаа хэтэрсэн 1 зүйл бий: Ном буцаах. Жагсаалтад бас 1 зүйл бий."
    )
    assert briefing.todo_sentence([item("Сүү авах")], TODAY) == "Жагсаалтад 1 зүйл байна: Сүү авах."
    assert briefing.todo_sentence([], TODAY) == "Хийх зүйлийн жагсаалт хоосон байна."


def test_briefing_with_what_the_phone_has_scheduled_today(client, planner):
    planner.then(("add_todo", {"user_request": "x", "title": "Тайлан илгээх", "due_at": "2026-10-06T23:59:00+08:00"}))
    client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()})

    planner.then(("daily_briefing", {"user_request": "Өдрийн тойм"}), ("list_reminders", {"user_request": "x"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Өнөөдөр юу байна?", "context": context()}).json()
    assert turn["stage"] == "awaiting_device"  # nothing is said before the phone lists its schedule

    def report(status, data=None):
        # The app reports every action: the briefing's inline result, then what the phone listed.
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [turn["actions"][0]["result"],
                        {"action_id": "a2", "tool": "list_reminders", "status": status, "executed_via": "react_native",
                         "error_code": None, "data": data}],
        })
        return r.json()["response"]

    scheduled = {"items": [
        {"id": "1", "title": "Уулзалт", "kind": "event", "fire_at": "2026-10-06T16:00:00+08:00"},
        {"id": "2", "title": "Сэрүүлэг", "kind": "alarm", "fire_at": "2026-10-07T07:00:00+08:00"},
    ]}
    said = report("succeeded", scheduled)
    assert said.startswith("Өдрийн мэнд! ")
    assert "Өнөөдөр хийх 1 зүйл байна: Тайлан илгээх." in said
    assert said.endswith("Өнөөдөр товлосон: өдөр 4 цагт Уулзалт.")  # tomorrow's alarm is left out


def test_briefing_says_nothing_about_a_schedule_it_cannot_see(client, planner):
    planner.then(("daily_briefing", {"user_request": "x"}), ("list_reminders", {"user_request": "x"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Өглөөний мэнд", "context": context()}).json()
    r = client.post("/api/v1/assistant/actions/results", json={
        "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
        "results": [turn["actions"][0]["result"],
                    {"action_id": "a2", "tool": "list_reminders", "status": "unsupported", "executed_via": None,
                     "error_code": "WEB_NO_IPHONE_ACTIONS"}],
    })
    said = r.json()["response"]
    assert said.startswith("Өдрийн мэнд! ") and "browser" not in said
