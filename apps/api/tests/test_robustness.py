"""When Gemini is out of quota or slow, and when the model's words would name a tool."""

from __future__ import annotations

from types import SimpleNamespace

from google.genai import errors

from bekhi_api import main as main_mod
from bekhi_api.providers import gemini

from .conftest import context


def quota_error() -> errors.ClientError:
    return errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})


class Models:
    def __init__(self, failures: int):
        self.failures, self.calls = failures, []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        if len(self.calls) <= self.failures:
            raise quota_error()
        return SimpleNamespace(text="ok")


async def test_a_per_minute_quota_is_waited_out_once(monkeypatch):
    monkeypatch.setattr(gemini, "QUOTA_RETRY_SECONDS", 0)
    monkeypatch.setattr(gemini, "_quota_exhausted_until", {})
    models = Models(failures=2)  # both models out of quota, then free again
    resp, model = await gemini._generate(SimpleNamespace(aio=SimpleNamespace(models=models)), ["a", "b"], contents=[],
                                         config=gemini.types.GenerateContentConfig(), thinking=False)
    assert resp.text == "ok" and len(models.calls) == 3

    still = Models(failures=99)
    try:
        await gemini._generate(SimpleNamespace(aio=SimpleNamespace(models=still)), ["a", "b"], contents=[],
                               config=gemini.types.GenerateContentConfig(), thinking=False)
        raise AssertionError("expected the quota error")
    except errors.ClientError as e:
        assert e.code == 429 and len(still.calls) == 4  # two rounds, no more


def test_out_of_quota_is_said_plainly(client, planner):
    async def busy(**kwargs):
        raise quota_error()

    planner.plan = busy
    r = client.post("/api/v1/assistant/chat", json={"text": "Сайн уу", "context": context()})
    assert r.status_code == 503 and r.json()["error"]["message"] == main_mod.MN_AI_BUSY


def test_tool_names_never_reach_the_user(client, planner):
    planner.then(("explain_limitation", {"user_request": "x", "code": "system_settings_toggle",
                                         "message": "Wi-Fi-г шууд асааж чадахгүй.", "alternative_kind": "open_settings",
                                         "alternative_description": "Тохиргоо руу орохын тулд open_app ашиглаж болно."}))
    said = client.post("/api/v1/assistant/chat", json={"text": "Wi-Fi асаа", "context": context()}).json()["response"]
    assert "open_app" not in said and "апп нээх" in said
