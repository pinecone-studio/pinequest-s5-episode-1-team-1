from datetime import datetime

import httpx
import pytest

from bekhi_api import todos

from .conftest import context

NOW = datetime.fromisoformat("2026-10-08T12:00:00+08:00")
ANA = "a" * 64  # sync accounts (sync.account_key)
BOLD = "b" * 64


@pytest.fixture(autouse=True)
def todo_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TODO_FILE", str(tmp_path / "todos.json"))


@pytest.fixture
def store():
    return todos.FileTodoStore()


async def test_add_list_complete_delete(store):
    async def titles(flt):
        return [i["title"] for i in (await todos.list_todos("l", {"filter": flt}, NOW, store, ANA)).data["items"]]

    await todos.add_todo("a1", {"title": "Сүү авах"}, NOW, store, ANA)
    await todos.add_todo("a2", {"title": "Ээж рүү залгах", "due_at": "2026-10-09T09:00:00+08:00"}, NOW, store, ANA)
    assert len(await titles("open")) == 2
    assert await titles("tomorrow") == ["Ээж рүү залгах"]
    assert await titles("overdue") == []

    assert (await todos.complete_todo("a6", {"query": "сүү"}, store, ANA)).status == "succeeded"
    assert await titles("done") == ["Сүү авах"]
    assert len(await titles("open")) == 1

    assert (await todos.delete_todo("a9", {"query": "ээж"}, store, ANA)).status == "succeeded"
    assert (await todos.list_todos("a10", {"filter": "all"}, NOW, store, ANA)).data["items"][0]["done"] is True


async def test_not_found_and_ambiguous(store):
    await todos.add_todo("a1", {"title": "Ном унших"}, NOW, store, ANA)
    await todos.add_todo("a2", {"title": "Ном худалдаж авах"}, NOW, store, ANA)
    assert (await todos.complete_todo("a3", {"query": "кино"}, store, ANA)).error_code == "TODO_NOT_FOUND"
    r = await todos.complete_todo("a4", {"query": "ном"}, store, ANA)
    assert (r.error_code, r.match_count) == ("TODO_AMBIGUOUS", 2)
    assert (await todos.delete_todo("a5", {"all": True}, store, ANA)).status == "succeeded"
    assert (await todos.list_todos("a6", {}, NOW, store, ANA)).data["items"] == []


async def test_each_account_has_its_own_list(store):
    await todos.add_todo("a1", {"title": "Сүү авах"}, NOW, store, ANA)
    await todos.add_todo("a2", {"title": "Тайлан бичих"}, NOW, store, BOLD)
    await todos.add_todo("a3", {"title": "Хуучин жагсаалт"}, NOW, store, None)

    async def titles(account):
        return [i["title"] for i in (await todos.list_todos("l", {"filter": "all"}, NOW, store, account)).data["items"]]

    assert await titles(ANA) == ["Сүү авах"]
    assert await titles(BOLD) == ["Тайлан бичих"]
    assert await titles(None) == ["Хуучин жагсаалт"]  # an app without a sync code
    assert (await todos.delete_todo("d", {"all": True}, store, ANA)).status == "succeeded"
    assert await titles(ANA) == [] and await titles(BOLD) == ["Тайлан бичих"]


async def test_supabase_store_scopes_every_call_to_the_account():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, dict(request.url.params)))
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": "1", "title": "Сүү авах", "due_at": None, "done": False,
                                              "created_at": "2026-10-08T12:00:00+08:00"}])
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        store = todos.make_store("https://x.supabase.co", "service", http)
        assert (await todos.complete_todo("c", {"query": "сүү"}, store, ANA)).status == "succeeded"
        assert (await todos.delete_todo("d", {"all": True}, store, ANA)).status == "succeeded"
    assert [m for m, _ in seen] == ["GET", "PATCH", "GET", "DELETE"]
    assert all(params["account_hash"] == f"eq.{ANA}" for _, params in seen)
    assert seen[1][1]["id"] == "in.(1)"
    assert "id" not in seen[3][1]  # "all" deletes by account, not a long id list


def test_the_api_keeps_a_list_per_sync_code(client, planner):
    def say(headers):
        r = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["response"]

    mine = {"X-Bekhi-Sync": "ABCD-EFGH-JKMN"}
    planner.then(("add_todo", {"user_request": "x", "title": "Сүү авах"}))
    say(mine)
    for headers, sees in ((mine, True), ({"X-Bekhi-Sync": "ZYXW-VTSR-QPNM"}, False), ({}, False)):
        planner.then(("list_todos", {"user_request": "x", "filter": "all"}))
        assert ("Сүү авах" in say(headers)) is sees
