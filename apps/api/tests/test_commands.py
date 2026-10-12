"""Commands between the user's linked devices: the phone asks, the computer does it (and back)."""

from __future__ import annotations

import asyncio

from bekhi_api import commands, desktop, sync

from .conftest import context

CODE = "ABCD-EFGH-JKMN"
PHONE = {"X-Bekhi-Sync": CODE, "X-Bekhi-Device": "android-1234567890"}
PC = {"X-Bekhi-Sync": CODE, "X-Bekhi-Device": "pc-1234567890"}
STRANGER = {"X-Bekhi-Sync": "ZYXW-VTSR-QPNM", "X-Bekhi-Device": "ios-1234567890"}
VOLUME_DOWN = {"target": "computer", "tool": "computer_control", "arguments": {"action": "volume_down"}}


def test_a_command_reaches_the_computer_and_its_outcome_comes_back(client):
    # Nobody is listening yet: the phone hears so at once instead of waiting.
    assert client.post("/api/v1/sync/commands", json=VOLUME_DOWN, headers=PHONE).json() == {"id": None}

    assert client.get("/api/v1/sync/commands", params={"target": "computer"}, headers=PC).json() == {"commands": []}
    sent = client.post("/api/v1/sync/commands", json=VOLUME_DOWN, headers=PHONE).json()
    assert sent["id"]
    # Another account never sees it.
    assert client.get("/api/v1/sync/commands", params={"target": "computer"}, headers=STRANGER).json() == {"commands": []}

    taken = client.get("/api/v1/sync/commands", params={"target": "computer"}, headers=PC).json()["commands"]
    assert taken == [{"id": sent["id"], "tool": "computer_control", "arguments": {"action": "volume_down"}, "from": "android"}]
    assert client.get("/api/v1/sync/commands", params={"target": "computer"}, headers=PC).json() == {"commands": []}

    outcome = {"status": "succeeded", "executed_via": "backend", "error_code": None, "data": {"volume": 40}}
    assert client.post(f"/api/v1/sync/commands/{sent['id']}/result", json=outcome, headers=PC).status_code == 200
    state = client.get(f"/api/v1/sync/commands/{sent['id']}", params={"wait": 1}, headers=PHONE).json()
    assert state == {"state": "done", "outcome": outcome}


def test_only_what_that_device_can_do_is_sent(client):
    client.get("/api/v1/sync/commands", params={"target": "phone"}, headers=PHONE)
    bad_tool = {"target": "phone", "tool": "computer_control", "arguments": {"action": "mute"}}
    assert client.post("/api/v1/sync/commands", json=bad_tool, headers=PC).status_code == 422
    bad_args = {"target": "phone", "tool": "call_contact", "arguments": {}}
    assert client.post("/api/v1/sync/commands", json=bad_args, headers=PC).status_code == 422
    call = {"target": "phone", "tool": "call_contact", "arguments": {"contact_name": "Ээж"}}
    assert client.post("/api/v1/sync/commands", json=call, headers=PC).json()["id"]


async def test_an_untaken_command_expires_instead_of_running_later(monkeypatch):
    store = commands.CommandStore()
    account = sync.account_key(CODE)
    await store.take(account, "computer", 0)
    cmd = store.send(account, "android-1", "computer", "type_text", {"text": "Сайн уу"})
    later = commands._now() + commands.PENDING_TTL * 2
    monkeypatch.setattr(commands, "_now", lambda: later)
    assert (await store.state(account, cmd.id, 0)).state == "expired"
    assert await store.take(account, "computer", 0) == []


async def test_the_pc_runs_what_the_phone_asks(tmp_path, monkeypatch):
    store = commands.CommandStore()
    ran = []
    monkeypatch.setattr(desktop, "run", lambda tool, args, s: ran.append((tool, args)) or {
        "status": "succeeded", "executed_via": "backend", "error_code": None, "data": None})
    pc = desktop.DesktopScheduler(tmp_path / "r.json", commands=store)
    pc.link(sync.account_key(CODE))
    serving = asyncio.create_task(pc._serve_commands(pc._take_here, pc._finish_here, "local"))
    try:
        for _ in range(50):  # until the PC is waiting for commands
            if store.listening(sync.account_key(CODE), "computer"):
                break
            await asyncio.sleep(0.01)
        cmd = store.send(sync.account_key(CODE), "android-1", "computer", "type_text", {"text": "Сайн байна уу"})
        done = await store.state(sync.account_key(CODE), cmd.id, 5)
    finally:
        serving.cancel()
    assert ran == [("type_text", {"text": "Сайн байна уу"})]
    assert done.state == "done" and done.outcome["status"] == "succeeded"


def test_typing_and_links_on_the_pc(tmp_path, monkeypatch):
    typed, opened = [], []
    monkeypatch.setattr(desktop.system.controls(), "type_text", lambda text: typed.append(text) or True)
    monkeypatch.setattr(desktop.system, "open_path", opened.append)
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("type_text", {"text": "Маргааш уулзъя."}, s)["status"] == "succeeded"
    assert desktop.run("open_url", {"url": "https://www.youtube.com/"}, s)["status"] == "handed_off"
    assert typed == ["Маргааш уулзъя."] and opened == ["https://www.youtube.com/"]


def test_this_pc_passes_a_command_on_to_the_cloud_when_the_phone_listens_there(client):
    class Cloud:
        def __init__(self):
            self.sent = []

        async def send(self, code, device, target, tool, args):
            self.sent.append((code, device, target, tool))
            return "11111111-2222-3333-4444-555555555555"

        async def state(self, code, device, command_id, wait):
            return {"state": "done", "outcome": {"status": "handed_off", "executed_via": "url_scheme",
                                                 "error_code": None, "data": None}}

    cloud = Cloud()
    client.app.state.remote_commands = cloud
    call = {"target": "phone", "tool": "call_contact", "arguments": {"contact_name": "Ээж"}}
    sent = client.post("/api/v1/sync/commands", json=call, headers=PC).json()
    assert sent["id"] == "11111111-2222-3333-4444-555555555555"
    assert cloud.sent == [(CODE, "pc-1234567890", "phone", "call_contact")]
    state = client.get(f"/api/v1/sync/commands/{sent['id']}", params={"wait": 1}, headers=PC).json()
    assert state["outcome"]["status"] == "handed_off"


def test_replies_say_which_device_did_it(client, planner):
    def report(tool, args, status, via, code=None, data=None):
        planner.then((tool, {"user_request": "x", **args}))
        turn = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}).json()
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [{"action_id": "a1", "tool": tool, "status": status, "executed_via": via,
                         "error_code": code, "data": data}],
        })
        return r.json()["response"]

    assert report("open_app", {"app_name": "VS Code", "device": "computer"}, "succeeded", "backend",
                  data={"device": "computer"}) == "За, компьютер дээр VS Code нээлээ."
    assert report("type_text", {"text": "Сайн уу"}, "succeeded", "backend", data={"device": "computer"}) == (
        "За, компьютер дээр бичлээ."
    )
    assert report("call_contact", {"contact_name": "Ээж", "confirmation_question": "?"}, "handed_off", "url_scheme",
                  data={"device": "phone"}).startswith("За, утсан дээр Ээж рүү")
    assert report("computer_control", {"action": "mute"}, "unsupported", None, "NO_COMPUTER").startswith(
        "Компьютер холбогдоогүй байна."
    )
