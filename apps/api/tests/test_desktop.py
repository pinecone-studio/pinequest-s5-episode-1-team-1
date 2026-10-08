from __future__ import annotations

from datetime import datetime, timedelta

from bekhi_api import desktop
from bekhi_api import main as main_mod

from .conftest import context

FUTURE = (datetime.now().astimezone() + timedelta(days=1)).replace(microsecond=0).isoformat()
PAST = (datetime.now().astimezone() - timedelta(hours=1)).replace(microsecond=0).isoformat()


def test_toast_xml_escapes_and_alarm_loops():
    xml = desktop.toast_xml("Ажил <чухал> & яаралтай", "BEKHI", alarm=True)
    assert "&lt;чухал&gt; &amp;" in xml
    assert 'scenario="alarm"' in xml and "Looping.Alarm" in xml
    assert 'scenario="reminder"' in desktop.toast_xml("a", "b", alarm=False)


def test_reminders_and_alarms_are_scheduled(tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    r = desktop.run("create_reminder", {"title": "Ажилтай", "due_at": FUTURE, "timezone": "Asia/Ulaanbaatar"}, s)
    assert r == {"status": "succeeded", "executed_via": "backend", "error_code": None, "data": None}
    desktop.run("create_alarm", {"fire_at": FUTURE, "timezone": "Asia/Ulaanbaatar"}, s)
    saved = desktop.DesktopScheduler(tmp_path / "r.json")._pending  # survives a restart
    assert [(t.title, t.alarm) for t in saved] == [("Ажилтай", False), ("Сэрэх цаг боллоо", True)]

    past = desktop.run("create_reminder", {"title": "x", "due_at": PAST, "timezone": "Asia/Ulaanbaatar"}, s)
    assert past["error_code"] == "TIME_IN_PAST"


async def test_due_toasts_fire_once(tmp_path, monkeypatch):
    shown = []

    async def fake_toast(title, body, alarm=False):
        shown.append((title, alarm))

    monkeypatch.setattr(desktop, "show_toast", fake_toast)
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    s.add(datetime.now().astimezone() + timedelta(minutes=5), "Ажилтай", "BEKHI", False)
    await s.fire_due(datetime.now())
    assert shown == []
    await s.fire_due(datetime.now() + timedelta(minutes=6))
    await s.fire_due(datetime.now() + timedelta(minutes=7))
    assert shown == [("Ажилтай", False)]


def test_notes_go_to_a_text_file(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "_documents_dir", lambda: tmp_path)
    r = desktop.run("create_note", {"title": "Дэлгүүр", "body": "Талх, сүү"}, desktop.DesktopScheduler(tmp_path / "r.json"))
    assert r["status"] == "succeeded"
    assert "Дэлгүүр\nТалх, сүү" in (tmp_path / desktop.NOTES_FILE_NAME).read_text(encoding="utf-8")


def test_notes_from_before_the_rename_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "_documents_dir", lambda: tmp_path)
    (tmp_path / desktop.OLD_NOTES_FILE_NAME).write_text("[хуучин]\nТалх\n\n", encoding="utf-8")
    desktop.run("create_note", {"title": "Шинэ", "body": "Сүү"}, desktop.DesktopScheduler(tmp_path / "r.json"))
    notes = (tmp_path / desktop.NOTES_FILE_NAME).read_text(encoding="utf-8")
    assert "Талх" in notes and "Сүү" in notes
    assert not (tmp_path / desktop.OLD_NOTES_FILE_NAME).exists()


def test_desktop_endpoint_is_local_only(client, tmp_path, monkeypatch):
    body = {"tool": "create_reminder", "arguments": {"title": "Ажилтай", "due_at": FUTURE, "timezone": "Asia/Ulaanbaatar"}}
    r = client.post("/api/v1/desktop/actions", json=body)
    assert r.status_code == 404  # no scheduler in tests, and the test client is not localhost

    client.app.state.desktop = desktop.DesktopScheduler(tmp_path / "r.json")
    assert client.post("/api/v1/desktop/actions", json=body).status_code == 404  # still not local
    monkeypatch.setattr(main_mod, "_is_local", lambda request: True)
    assert client.post("/api/v1/desktop/actions", json=body).json()["status"] == "succeeded"
    bad = {"tool": "create_reminder", "arguments": {"title": "Ажилтай"}}
    assert client.post("/api/v1/desktop/actions", json=bad).status_code == 422


def test_desktop_outcomes_say_computer(client, planner):
    planner.then(("create_alarm", {"user_request": "7 цагт сэрээх", "fire_at": "2026-10-07T07:00:00+08:00", "timezone": "Asia/Ulaanbaatar"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "7 цагт сэрээ", "context": context()}).json()
    r = client.post("/api/v1/assistant/actions/results", json={
        "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
        "results": [{"action_id": "a1", "tool": "create_alarm", "status": "succeeded", "executed_via": "backend", "error_code": None}],
    })
    assert "компьютер дээр сэрүүлэг" in r.json()["response"]


def test_timers_lists_and_cancelling(tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    soon = (datetime.now().astimezone() + timedelta(hours=2)).replace(microsecond=0)
    desktop.run("create_reminder", {"title": "Ус уух", "due_at": soon.isoformat(), "timezone": "Asia/Ulaanbaatar"}, s)
    desktop.run("create_reminder", {"title": "Ажилтай", "due_at": FUTURE, "timezone": "Asia/Ulaanbaatar"}, s)
    desktop.run("set_timer", {"duration_seconds": 600}, s)

    items = desktop.run("list_reminders", {}, s)["data"]["items"]
    assert [(i["title"], i["kind"]) for i in items] == [("Таймер", "timer"), ("Ус уух", "reminder"), ("Ажилтай", "reminder")]
    assert items[1]["fire_at"] == soon.isoformat()  # with this PC's offset, read as local wall time

    ambiguous = desktop.run("cancel_reminder", {}, s)
    assert ambiguous["status"] == "needs_clarification" and ambiguous["match_count"] == 3
    assert desktop.run("cancel_reminder", {"query": "Кино"}, s)["error_code"] == "REMINDER_NOT_FOUND"
    assert desktop.run("cancel_reminder", {"query": "ус уух"}, s)["data"]["cancelled"] == ["Ус уух"]
    assert desktop.run("cancel_reminder", {"at": FUTURE}, s)["data"]["cancelled"] == ["Ажилтай"]
    assert desktop.run("cancel_reminder", {"all": True}, s)["data"]["cancelled"] == ["Таймер"]
    assert desktop.run("list_reminders", {}, s)["data"] == {"items": []}


def test_computer_control(monkeypatch):
    from bekhi_api import windows_controls as win

    calls, opened = [], []
    monkeypatch.setattr(win, "change_volume", lambda **kw: calls.append(kw) or 40)
    monkeypatch.setattr(win, "lock_screen", lambda: True)
    monkeypatch.setattr(win, "known_folder", lambda name: f"C:/Users/x/{name}")
    monkeypatch.setattr(desktop.os, "startfile", opened.append, raising=False)

    up = desktop.computer_control({"action": "volume_up"})
    assert up["status"] == "succeeded" and up["data"] == {"volume": 40} and calls[-1] == {"delta": 10}
    desktop.computer_control({"action": "set_volume", "level": 40})
    assert calls[-1] == {"level": 40}
    assert desktop.computer_control({"action": "set_volume"})["error_code"] == "INVALID_ARGUMENTS"
    desktop.computer_control({"action": "mute"})
    assert calls[-1] == {"mute": True}
    assert desktop.computer_control({"action": "lock_screen"})["status"] == "succeeded"
    desktop.computer_control({"action": "open_folder", "folder": "downloads"})
    assert opened == ["C:/Users/x/downloads"]

    def no_speakers(**kw):
        raise OSError(-2147023728, "no device")

    monkeypatch.setattr(win, "change_volume", no_speakers)
    assert desktop.computer_control({"action": "volume_down"})["error_code"] == "VOLUME_UNAVAILABLE"


def test_new_tool_sentences(client, planner):
    def said(tool, args, result, text="x"):
        planner.then((tool, {"user_request": text, **args}))
        turn = client.post("/api/v1/assistant/chat", json={"text": text, "context": context()}).json()
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [{"action_id": "a1", "tool": tool, **result}],
        })
        return r.json()["response"]

    ok_pc = {"status": "succeeded", "executed_via": "backend", "error_code": None}
    assert said("set_timer", {"duration_seconds": 5400}, ok_pc) == "За, 1 цаг 30 минутын таймер тавилаа. Компьютер дээр дуугарна."
    assert "чимээгүй" in said("set_timer", {"duration_seconds": 600}, {**ok_pc, "executed_via": "react_native"})
    items = [{"id": "1", "title": "Ус уух", "kind": "reminder", "fire_at": "2026-10-06T20:00:00+08:00"}]
    assert said("list_reminders", {}, {**ok_pc, "data": {"items": items}}) == "Танд 1 зүйл товлогдсон байна: өнөөдөр орой 8 цагт Ус уух."
    assert "алга" in said("list_reminders", {}, {**ok_pc, "data": {"items": []}})
    assert said("cancel_reminder", {"query": "ус"}, {**ok_pc, "data": {"cancelled": ["Ус уух"]}}) == "За, Ус уух цуцаллаа."
    assert "Алийг нь" in said("cancel_reminder", {}, {"status": "needs_clarification", "executed_via": "backend", "error_code": None, "match_count": 3})
    assert said("computer_control", {"action": "volume_up"}, {**ok_pc, "data": {"volume": 40}}) == "За, дууг нэмлээ. Одоо 40% байна."
    assert said("computer_control", {"action": "open_folder", "folder": "downloads"}, ok_pc) == "За, Downloads хавтсыг нээлээ."
    assert "iOS" in said("computer_control", {"action": "lock_screen"}, {"status": "unsupported", "executed_via": None, "error_code": "IOS_NO_SYSTEM_CONTROL"})
    assert "Android" in said("computer_control", {"action": "volume_up"}, {"status": "unsupported", "executed_via": None, "error_code": "ANDROID_NO_SYSTEM_CONTROL"})
