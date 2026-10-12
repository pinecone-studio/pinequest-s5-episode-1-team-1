from datetime import datetime

import pytest

from bekhi_api import memory

from .conftest import context

NOW = datetime.fromisoformat("2026-10-08T12:00:00+08:00")
ANA = "a" * 64


@pytest.fixture(autouse=True)
def memory_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_FILE", str(tmp_path / "memory.json"))


async def test_remember_and_forget():
    store = memory.FileFactStore()
    said = lambda r: r.data["summary_mn"] if r.data else r.error_code  # noqa: E731
    assert said(await memory.remember("a", {"fact": "Хэрэглэгчийн эхнэрийг Сараа гэдэг"}, NOW, store, ANA)) == "За, санаж авлаа."
    assert said(await memory.remember("a", {"fact": "хэрэглэгчийн эхнэрийг Сараа гэдэг."}, NOW, store, ANA)) == "За, үүнийг санаж байгаа."
    await memory.remember("a", {"fact": "Хэрэглэгч Баянзүрх дүүрэгт амьдардаг"}, NOW, store, ANA)
    assert await memory.facts_for(store, ANA) == ["Хэрэглэгчийн эхнэрийг Сараа гэдэг", "Хэрэглэгч Баянзүрх дүүрэгт амьдардаг"]
    assert await memory.facts_for(store, None) == []  # another account (no code) sees none of it

    assert said(await memory.forget("f", {"query": "эхнэрийн"}, store, ANA)) == "За, мартлаа."  # by word stem
    assert said(await memory.forget("f", {"query": "машин"}, store, ANA)) == "MEMORY_NOT_FOUND"
    assert await memory.facts_for(store, ANA) == ["Хэрэглэгч Баянзүрх дүүрэгт амьдардаг"]
    assert said(await memory.forget("f", {"all": True}, store, ANA)) == "За, санасан бүх зүйлээ мартлаа."
    assert await memory.facts_for(store, ANA) == []


def test_the_planner_is_told_what_the_account_remembers(client, planner):
    mine = {"X-Bekhi-Sync": "ABCD-EFGH-JKMN"}
    planner.then(("remember", {"user_request": "x", "fact": "Хэрэглэгчийн дүүг Тэмүүлэн гэдэг"}))
    r = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}, headers=mine)
    assert r.json()["response"] == "За, санаж авлаа."

    for headers, knows in ((mine, True), ({"X-Bekhi-Sync": "ZYXW-VTSR-QPNM"}, False)):
        planner.then(("reply", {"user_request": "x", "text": "ok"}))
        client.post("/api/v1/assistant/chat", json={"text": "Дүү рүүгээ залга", "context": context()}, headers=headers)
        assert ("Хэрэглэгчийн дүүг Тэмүүлэн гэдэг" in planner.systems[-1]) is knows
