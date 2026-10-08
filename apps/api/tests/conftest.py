from __future__ import annotations

import os
from typing import Any

# Tests never touch this PC: no desktop scheduler, real toasts or notes file.
os.environ["DESKTOP_ACTIONS"] = "false"

import httpx
import pytest
from fastapi.testclient import TestClient

from bekhi_api import main as main_mod
from bekhi_api.providers.base import FunctionCall, HistoryMessage

NOW = "2026-10-06T14:00:00+08:00"


def context(conversation_id: str | None = None, platform: str = "ios") -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "client_now": NOW,
        "timezone": "Asia/Ulaanbaatar",
        "response_language": "mn",
        "tts_voice": "female",
        "device": {
            "platform": platform,
            "os_version": "26.1",
            "app_version": "0.1.0",
            "permissions": {k: "granted" for k in ("microphone", "contacts", "calendar", "reminders", "notifications", "alarms")},
            "features": {"alarmkit": True, "app_intents": True, "shortcuts": True, "message_compose": True, "google_maps_installed": False},
        },
    }


class FakePlanner:
    """Returns scripted function calls and records what it was given."""

    def __init__(self) -> None:
        self.script: list[list[FunctionCall]] = []
        self.after: list[list[FunctionCall]] = []
        self.histories: list[list[HistoryMessage]] = []
        self.systems: list[str] = []
        self.followups: list[list[tuple[FunctionCall, dict[str, Any]]]] = []

    def then(self, *calls: tuple[str, dict[str, Any]]) -> "FakePlanner":
        self.script.append([FunctionCall(name, args) for name, args in calls])
        return self

    def after_tools(self, *calls: tuple[str, dict[str, Any]]) -> "FakePlanner":
        """What the model calls once it has the results of its backend tools (agent loop)."""
        self.after.append([FunctionCall(name, args) for name, args in calls])
        return self

    async def plan(self, *, system, history, user_text, functions):
        self.histories.append(list(history))
        self.systems.append(system)
        return self.script.pop(0)

    async def follow_up(self, results):
        self.followups.append(results)
        return self.after.pop(0) if self.after else []


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        return self.text


def open_meteo(request: httpx.Request) -> httpx.Response:
    if "forecast" in request.url.path:
        return httpx.Response(200, json={"daily": {
            "weather_code": [61], "temperature_2m_max": [9.4], "temperature_2m_min": [-2.6],
            "precipitation_probability_max": [70],
        }})
    return httpx.Response(200, json={"results": [{"name": "Дархан", "latitude": 49.48, "longitude": 105.96}]})


@pytest.fixture
def planner(monkeypatch) -> FakePlanner:
    fake = FakePlanner()
    monkeypatch.setattr(main_mod, "get_llm", lambda: fake)
    return fake


@pytest.fixture
def client(planner):
    app = main_mod.create_app()  # fresh rate-limit window and TTS cache for every test
    with TestClient(app) as c:
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(open_meteo))
        yield c
