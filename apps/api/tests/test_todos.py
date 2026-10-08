from datetime import datetime

import pytest

from bekhi_api import todos

NOW = datetime.fromisoformat("2026-10-08T12:00:00+08:00")


@pytest.fixture(autouse=True)
def todo_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TODO_FILE", str(tmp_path / "todos.json"))


def test_add_list_complete_delete():
    todos.add_todo("a1", {"title": "Сүү авах"}, NOW)
    todos.add_todo("a2", {"title": "Ээж рүү залгах", "due_at": "2026-10-09T09:00:00+08:00"}, NOW)
    assert len(todos.list_todos("a3", {"filter": "open"}, NOW).data["items"]) == 2
    assert [i["title"] for i in todos.list_todos("a4", {"filter": "tomorrow"}, NOW).data["items"]] == ["Ээж рүү залгах"]
    assert todos.list_todos("a5", {"filter": "overdue"}, NOW).data["items"] == []

    assert todos.complete_todo("a6", {"query": "сүү"}).status == "succeeded"
    assert [i["title"] for i in todos.list_todos("a7", {"filter": "done"}, NOW).data["items"]] == ["Сүү авах"]
    assert len(todos.list_todos("a8", {"filter": "open"}, NOW).data["items"]) == 1

    assert todos.delete_todo("a9", {"query": "ээж"}).status == "succeeded"
    assert todos.list_todos("a10", {"filter": "all"}, NOW).data["items"][0]["done"] is True


def test_not_found_and_ambiguous():
    todos.add_todo("a1", {"title": "Ном унших"}, NOW)
    todos.add_todo("a2", {"title": "Ном худалдаж авах"}, NOW)
    assert todos.complete_todo("a3", {"query": "кино"}).error_code == "TODO_NOT_FOUND"
    r = todos.complete_todo("a4", {"query": "ном"})
    assert (r.error_code, r.match_count) == ("TODO_AMBIGUOUS", 2)
    assert todos.delete_todo("a5", {"all": True}).status == "succeeded"
    assert todos.list_todos("a6", {}, NOW).data["items"] == []
