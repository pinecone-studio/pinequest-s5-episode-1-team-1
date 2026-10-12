"""The user's profile: name, city and what the day's briefing tells, one per account."""

from __future__ import annotations

import httpx
import pytest

from bekhi_api import backend_tools
from bekhi_api import profile as profiles
from bekhi_api.models import ActionResult

from .conftest import context

CODE = {"X-Bekhi-Sync": "ABCDEFGHJKMN", "X-Bekhi-Device": "ios-1234567890abcdef"}


@pytest.fixture(autouse=True)
def profile_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFILE_FILE", str(tmp_path / "profile.json"))


async def test_changes_merge_and_parts_keep_bekhis_order():
    store = profiles.FileProfileStore()
    assert profiles.briefing_parts(await store.get("a")) == ["weather", "todos", "schedule"]  # not chosen yet
    await profiles.update(store, "a", {"name": "Нандин", "briefing_add": ["news", "email"]})
    p = await profiles.update(store, "a", {"city": "Дархан", "briefing_remove": ["schedule"]})
    assert p == {"name": "Нандин", "city": "Дархан", "briefing": ["weather", "todos", "email", "news"]}
    assert (await profiles.update(store, "a", {"name": ""})).get("name") is None
    assert await store.get("b") == {}  # another account knows nothing of it
    assert profiles.prompt_line(p) == ("About the user: their name is Нандин; they live in Дархан "
                                       "(the weather's place when they name none).")


async def test_a_database_without_the_profiles_table_keeps_them_in_a_file():
    calls = []

    def missing(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(404, json={"code": "PGRST205", "message": "Could not find the table 'public.profiles'"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(missing)) as http:
        store = profiles.SupabaseProfileStore("https://x.supabase.co", "sb_secret_x", http, profiles.FileProfileStore())
        await profiles.update(store, "a", {"city": "Эрдэнэт"})
        assert (await store.get("a")) == {"city": "Эрдэнэт"}
    assert calls == ["GET"]  # asked once, then the file


def test_the_app_reads_and_changes_the_profile(client):
    assert client.get("/api/v1/profile", headers=CODE).json()["briefing"] is None
    r = client.post("/api/v1/profile", headers=CODE, json={"briefing": ["news", "weather"], "city": "Ховд"})
    assert r.json() == {"name": None, "city": "Ховд", "briefing": ["weather", "news"]}
    got = client.get("/api/v1/profile", headers=CODE).json()
    assert got["briefing"] == ["weather", "news"] and got["parts"] == list(profiles.BRIEFING_PARTS)
    assert client.post("/api/v1/profile", headers=CODE, json={"briefing": ["movies"]}).status_code == 422
    assert client.get("/api/v1/profile").status_code == 401  # no sync code, no profile


def test_the_weather_is_for_the_users_city_when_they_name_none(client, planner, monkeypatch):
    client.post("/api/v1/profile", headers=CODE, json={"city": "Дархан"})
    asked = []

    async def weather(action_id, args, now, http):
        asked.append(args.get("location_name"))
        return ActionResult(action_id=action_id, tool="get_weather", status="succeeded", executed_via="backend",
                            error_code=None, data={"summary_mn": "Дулаан."})

    monkeypatch.setattr(backend_tools, "get_weather", weather)
    planner.then(("get_weather", {"user_request": "x"}))
    client.post("/api/v1/assistant/chat", headers=CODE, json={"text": "Цаг агаар ямар байна?", "context": context()})
    planner.then(("get_weather", {"user_request": "x", "location_name": "Улаанбаатар"}))
    client.post("/api/v1/assistant/chat", headers=CODE, json={"text": "УБ-д ямар байна?", "context": context()})
    assert asked == ["Дархан", "Улаанбаатар"]
    assert "they live in Дархан" in planner.systems[-1]  # the planner knows it too
