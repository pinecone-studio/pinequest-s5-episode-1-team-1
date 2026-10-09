"""BEKHI's PC agent (agent.py): the cloud web app's PC actions run here, and alarms set on the
user's other devices are pulled from the cloud API."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from bekhi_api import agent, desktop, sync
from bekhi_api import main as main_mod
from bekhi_api.config import get_settings

CODE = "ABCD-EFGH-JKMN"


def in_hours(h: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).replace(microsecond=0).isoformat()


def fake_cloud(store: sync.MemorySyncStore, seen: list[tuple[str, str, str]]):
    """The cloud API's sync endpoints, over a MemorySyncStore."""

    async def handler(request: httpx.Request) -> httpx.Response:
        code, device = request.headers.get("x-bekhi-sync"), request.headers.get("x-bekhi-device") or ""
        seen.append((request.method, request.url.path, device))
        account, now = sync.account_key(code), datetime.now(timezone.utc)
        if account is None or not sync.valid_device_id(device):
            return httpx.Response(401)
        body = json.loads(request.content) if request.content else {}
        match request.method, request.url.path:
            case "POST", "/api/v1/sync/devices":
                await store.touch_device(account, device, body["platform"], now)
                return httpx.Response(200, json={"ok": True})
            case "GET", "/api/v1/sync/alarms":
                active, cancelled = await store.pull(account, now)
                return httpx.Response(200, json={"active": active, "cancelled": cancelled})
        return httpx.Response(404)

    return handler


async def test_the_agent_rings_alarms_set_on_the_phone_through_the_cloud(tmp_path):
    cloud, seen = sync.MemorySyncStore(), []
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_cloud(cloud, seen))) as http:
        remote = sync.make_store(None, None, http, "https://cloud.example")
        assert isinstance(remote, sync.RemoteSyncStore)
        pc = desktop.DesktopScheduler(tmp_path / "r.json", sync=remote)
        pc.link(CODE)  # the agent keeps the code itself; the cloud hashes it

        alarm_id = str(uuid4())
        await cloud.publish(sync.account_key(CODE), "phone-1234567890",
                            {"id": alarm_id, "kind": "alarm", "title": "Сэрэх цаг боллоо", "fire_at": in_hours(8)})
        await pc.sync_now()
        assert [(i["kind"], i["sync_id"]) for i in pc.items()] == [("alarm", alarm_id)]

        await cloud.cancel(sync.account_key(CODE), [alarm_id], datetime.now(timezone.utc))
        await pc.sync_now()
        assert pc.items() == []
    assert {(m, p) for m, p, _ in seen} == {("POST", "/api/v1/sync/devices"), ("GET", "/api/v1/sync/alarms")}
    assert all(device.startswith("pc-") for _, _, device in seen)


def test_the_agent_links_the_pc_with_the_code_itself(client, tmp_path, monkeypatch):
    client.app.state.sync = sync.RemoteSyncStore("https://cloud.example", client.app.state.http)
    client.app.state.desktop = desktop.DesktopScheduler(tmp_path / "r.json", sync=client.app.state.sync)
    monkeypatch.setattr(main_mod, "_is_local", lambda request: True)
    monkeypatch.setattr(client.app.state.desktop, "sync_now", lambda: _noop())
    r = client.post("/api/v1/desktop/sync", json={"code": CODE})
    assert r.status_code == 200 and r.json()["device_id"].startswith("pc-")
    assert json.loads((tmp_path / "sync.json").read_text(encoding="utf-8"))["account"] == CODE


async def _noop() -> None:
    return None


def test_the_cloud_web_app_may_call_the_agent(monkeypatch):
    monkeypatch.setenv("DESKTOP_ACTIONS", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://bekhi.pages.dev")
    get_settings.cache_clear()
    try:
        app = main_mod.create_app()  # no lifespan: nothing is scheduled on this PC
        r = TestClient(app).options("/api/v1/desktop/actions", headers={
            "Origin": "https://bekhi.pages.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Private-Network": "true",
        })
    finally:
        get_settings.cache_clear()
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://bekhi.pages.dev"
    assert r.headers["access-control-allow-private-network"] == "true"


def test_agent_serves_this_pc_for_the_cloud_web_app(monkeypatch):
    ran = {}
    monkeypatch.setattr(agent.uvicorn, "run", lambda app, **kw: ran.update(app=app, **kw))
    env = {k: v for k, v in os.environ.items() if k != "SYNC_API_URL"}
    monkeypatch.setattr(os, "environ", {**env, "CORS_ORIGINS": "http://localhost:19006"})  # restored afterwards
    agent.main()
    assert ran == {"app": "bekhi_api.main:app", "host": "127.0.0.1", "port": 8000, "log_level": "warning"}
    assert os.environ["SYNC_API_URL"] == agent.CLOUD_API
    assert os.environ["CORS_ORIGINS"].split(",") == ["http://localhost:19006", agent.CLOUD_WEB, "http://localhost:8081"]
