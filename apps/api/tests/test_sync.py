"""Alarms and timers shared between linked devices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from bekhi_api import desktop, pipeline, sync
from bekhi_api.planner import function_specs

from .conftest import context

CODE = "ABCD-EFGH-JKMN"
PHONE = {"X-Bekhi-Sync": CODE, "X-Bekhi-Device": "phone-1234567890"}
PC = {"X-Bekhi-Sync": "abcd efgh jkmn", "X-Bekhi-Device": "pc-1234567890"}  # same code, typed loosely


def in_hours(h: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).replace(microsecond=0).isoformat()


def test_sync_codes_are_normalized_and_validated():
    assert sync.account_key("ABCD-EFGH-JKMN") == sync.account_key("abcdefghjkmn")
    assert sync.account_key("ABCD-EFGH-JKMO") == sync.account_key("ABCD-EFGH-JKM0")  # O reads as 0
    assert sync.account_key("ABCD-EFGH-JKMU") is None  # U is not in the alphabet
    assert sync.account_key("ABCD-EFGH") is None
    assert sync.account_key(None) is None


def test_devices_share_alarms_and_cancellations(client):
    assert client.post("/api/v1/sync/devices", json={"platform": "ios"}, headers=PHONE).status_code == 200
    assert client.post("/api/v1/sync/devices", json={"platform": "web"}, headers=PC).status_code == 200

    alarm = {"id": str(uuid4()), "kind": "alarm", "title": "Сэрэх цаг боллоо", "fire_at": in_hours(8)}
    r = client.post("/api/v1/sync/alarms", json=alarm, headers=PHONE)
    assert r.json() == {"other_devices": ["web"]}  # the reply can say where else it went

    pulled = client.get("/api/v1/sync/alarms", headers=PC).json()
    assert [a["id"] for a in pulled["active"]] == [alarm["id"]] and pulled["cancelled"] == []

    client.post("/api/v1/sync/alarms/cancel", json={"ids": [alarm["id"]]}, headers=PC)
    pulled = client.get("/api/v1/sync/alarms", headers=PHONE).json()
    assert pulled == {"active": [], "cancelled": [alarm["id"]]}


def test_sync_needs_a_valid_code_and_keeps_accounts_apart(client):
    assert client.get("/api/v1/sync/alarms", headers={"X-Bekhi-Device": "phone-1234567890"}).status_code == 401
    assert client.get("/api/v1/sync/alarms", headers={**PHONE, "X-Bekhi-Device": "x"}).status_code == 401
    alarm = {"id": str(uuid4()), "kind": "timer", "title": "Таймер", "fire_at": in_hours(1)}
    client.post("/api/v1/sync/alarms", json=alarm, headers=PHONE)
    other = {"X-Bekhi-Sync": "ZZZZ-ZZZZ-ZZZZ", "X-Bekhi-Device": "phone-0987654321"}
    assert client.get("/api/v1/sync/alarms", headers=other).json() == {"active": [], "cancelled": []}


async def test_past_alarms_are_dropped():
    store = sync.MemorySyncStore()
    now = datetime.now(timezone.utc)
    await store.publish("acc", "dev", {"id": "old", "kind": "alarm", "title": "x", "fire_at": (now - timedelta(minutes=1)).isoformat()})
    assert await store.pull("acc", now) == ([], [])


def test_model_does_not_see_backend_fields():
    specs = {f.name: f.parameters["properties"] for f in function_specs()}
    assert "target" in specs["set_timer"] and "target" in specs["create_alarm"]
    assert not {"sync_id", "fire_at"} & set(specs["set_timer"])
    assert "sync_id" not in specs["create_alarm"] and "fire_at" in specs["create_alarm"]


def test_timer_end_comes_from_the_server_clock(client, planner, monkeypatch):
    server_now = datetime(2026, 10, 6, 6, 0, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline, "_server_now", lambda: server_now)
    planner.then(("set_timer", {"user_request": "10 минутын таймер", "duration_seconds": 600,
                                "fire_at": "2030-01-01T00:00:00+08:00", "sync_id": "not-from-the-model"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "10 минутын таймер", "context": context()}).json()
    args = turn["actions"][0]["arguments"]
    assert args["fire_at"] == "2026-10-06T14:10:30+08:00"  # server time + 10 min, in the user's offset
    assert args["target"] == "all" and UUID(args["sync_id"])


def test_this_device_only_gets_no_sync_id(client, planner):
    planner.then(("create_alarm", {"user_request": "зөвхөн утсан дээр 7-д сэрээ", "fire_at": "2026-10-07T07:00:00+08:00",
                                   "timezone": "Asia/Ulaanbaatar", "target": "this"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}).json()
    assert "sync_id" not in turn["actions"][0]["arguments"]


def test_reply_says_where_else_it_went(client, planner):
    def said(data):
        planner.then(("create_alarm", {"user_request": "7-д сэрээ", "fire_at": "2026-10-07T07:00:00+08:00",
                                       "timezone": "Asia/Ulaanbaatar"}))
        turn = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}).json()
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [{"action_id": "a1", "tool": "create_alarm", "status": "succeeded",
                         "executed_via": "react_native", "error_code": None, "data": data}],
        })
        return r.json()["response"]

    assert said({"sync": {"status": "sent", "other_devices": ["web", "android"]}}).endswith(
        "Бусад төхөөрөмж рүү бас илгээлээ: компьютер, Android утас."
    )
    assert said({"sync": {"status": "failed"}}).endswith("зөвхөн энд тавигдлаа.")
    assert "Бусад" not in said({"sync": {"status": "sent", "other_devices": []}})  # nothing else is linked
    assert "Бусад" not in said(None)  # target "this", or no sync code


async def test_pc_rings_alarms_set_on_the_phone(tmp_path):
    store = sync.MemorySyncStore()
    s = desktop.DesktopScheduler(tmp_path / "r.json", sync=store)
    account = sync.account_key(CODE)
    device = s.link(account)
    assert device.startswith("pc-") and desktop.DesktopScheduler(tmp_path / "r.json").link(account) == device

    alarm_id, soon_id = str(uuid4()), str(uuid4())
    await store.publish(account, "phone", {"id": alarm_id, "kind": "alarm", "title": "Сэрэх цаг боллоо", "fire_at": in_hours(8)})
    await store.publish(account, "phone", {"id": soon_id, "kind": "timer", "title": "Таймер", "fire_at": in_hours(0.0005)})
    await s.sync_now()
    await s.sync_now()  # pulling again does not add a second copy
    items = s.items()
    assert [(i["kind"], i["sync_id"]) for i in items] == [("alarm", alarm_id)]  # ringing within seconds: skipped
    assert await store.other_devices(account, "phone", datetime.now(timezone.utc)) == ["web"]

    await store.cancel(account, [alarm_id], datetime.now(timezone.utc))
    await s.sync_now()
    assert s.items() == []


def test_pc_cancel_reports_synced_ids(tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    sid = str(uuid4())
    desktop.run("set_timer", {"duration_seconds": 600, "fire_at": in_hours(0.2), "sync_id": sid}, s)
    desktop.run("create_alarm", {"fire_at": in_hours(5), "timezone": "Asia/Ulaanbaatar"}, s)
    data = desktop.run("cancel_reminder", {"all": True}, s)["data"]
    assert data["cancelled_sync_ids"] == [sid]


def test_reply_says_when_cancelling_elsewhere_failed(client, planner):
    planner.then(("cancel_reminder", {"user_request": "сэрүүлгээ болиул", "query": "сэрэх"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}).json()
    r = client.post("/api/v1/assistant/actions/results", json={
        "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
        "results": [{"action_id": "a1", "tool": "cancel_reminder", "status": "succeeded", "executed_via": "react_native",
                     "error_code": None, "data": {"cancelled": ["Сэрэх цаг боллоо"], "sync": {"status": "failed"}}}],
    })
    assert r.json()["response"] == "За, Сэрэх цаг боллоо цуцаллаа. Гэхдээ бусад төхөөрөмж дээр цуцалж чадсангүй."
