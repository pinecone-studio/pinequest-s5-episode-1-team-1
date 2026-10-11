"""The agent's computer and web tools: find, open and read the user's files, read web pages."""

from __future__ import annotations

import os
import zipfile

import httpx
import pytest

from bekhi_api import pc_files, webpage

from .conftest import context


@pytest.fixture
def folders(tmp_path, monkeypatch):
    downloads, documents = tmp_path / "Downloads", tmp_path / "Documents"
    (documents / "Ажил" / "2026").mkdir(parents=True)
    downloads.mkdir()
    files = {
        downloads / "Tailan_sar.pdf": 300,
        downloads / "setup.exe": 400,  # a program: never listed or opened
        documents / "Ажил" / "2026" / "тайлан.docx": 200,
        documents / "notes.txt": 100,
    }
    for i, (path, age) in enumerate(files.items()):
        if path.suffix == ".docx":
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("word/document.xml", "<w:document><w:p><w:t>Сарын тайлан</w:t></w:p><w:p><w:t>Орлого 5 сая</w:t></w:p></w:document>")
        else:
            path.write_text("Маргааш 10 цагт уулзалт." if path.suffix == ".txt" else f"file {i}", encoding="utf-8")
        os.utime(path, (1_800_000_000 - age, 1_800_000_000 - age))
    monkeypatch.setattr(pc_files, "_found", {})
    monkeypatch.setattr(pc_files, "_next_id", 0)  # ids start again at f1
    roots = {"downloads": downloads, "documents": documents}
    monkeypatch.setattr(pc_files, "_folder_path", lambda f: roots.get(f) or (_ for _ in ()).throw(OSError()))
    return roots


def names(result):
    return [f["name"] for f in result.data["files"]]


def test_files_are_found_by_name_in_either_script_newest_first(folders):
    assert names(pc_files.find_files("a", {"query": "тайлан"})) == ["тайлан.docx", "Tailan_sar.pdf"]
    assert names(pc_files.find_files("a", {"folder": "downloads", "kind": "pdf"})) == ["Tailan_sar.pdf"]
    assert "setup.exe" not in names(pc_files.find_files("a", {}))
    assert pc_files.find_files("a", {"query": "кино"}).data["summary_mn"] == "Тийм файл олдсонгүй."


def test_only_found_files_open_and_text_files_are_read(folders, monkeypatch):
    opened = []
    monkeypatch.setattr(pc_files.os, "startfile", opened.append, raising=False)
    found = pc_files.find_files("a", {"query": "тайлан"}).data["files"]
    assert pc_files.open_file("o", {"file": found[1]["id"]}).status == "succeeded"
    assert [p.name for p in opened] == ["Tailan_sar.pdf"]
    assert pc_files.open_file("o", {"file": "f9999"}).error_code == "FILE_NOT_FOUND"

    assert pc_files.read_file("r", {"file": found[0]["id"]}).data["text"] == "Сарын тайлан\nОрлого 5 сая"
    assert pc_files.read_file("r", {"file": found[1]["id"]}).error_code == "FILE_UNREADABLE"  # a PDF


def test_web_pages_are_read_but_never_private_addresses(monkeypatch):
    html = "<html><head><title>BEKHI мэдээ</title><script>x()</script></head><body><h1>Гарчиг</h1><p>Өнөөдөр нартай.</p></body></html>"

    async def public(host):
        return host == "news.example"

    monkeypatch.setattr(webpage, "_public", public)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go-inside":
            return httpx.Response(302, headers={"location": "https://intranet.example/secret"})
        return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            ok = await webpage.read_webpage("w", {"url": "https://news.example/a"}, http)
            inside = await webpage.read_webpage("w", {"url": "https://news.example/go-inside"}, http)
            private = await webpage.read_webpage("w", {"url": "https://intranet.example/"}, http)
        return ok, inside, private

    import asyncio

    ok, inside, private = asyncio.run(run())
    assert ok.data["title"] == "BEKHI мэдээ" and ok.data["text"] == "Гарчиг\nӨнөөдөр нартай."
    assert inside.error_code == "URL_NOT_ALLOWED" and private.error_code == "URL_NOT_ALLOWED"


def test_the_agent_finds_then_opens_a_file_on_the_computer(client, planner, folders, monkeypatch):
    opened = []
    monkeypatch.setattr(pc_files.os, "startfile", opened.append, raising=False)
    class ThisPc:  # this API runs on the user's computer
        async def stop(self):
            pass

    client.app.state.desktop = ThisPc()
    planner.then(("find_files", {"user_request": "x", "folder": "downloads", "kind": "pdf"}))
    planner.after_tools(("open_file", {"user_request": "x", "file": "f1"}))
    planner.after_tools(("reply", {"user_request": "x", "text": "За, Tailan_sar.pdf-ийг нээлээ."}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Downloads-ийн сүүлийн PDF-ийг нээ",
                                                       "context": context(platform="web")}).json()
    # The model saw what find_files found, opened it by its id, then answered.
    assert [f["name"] for f in planner.followups[0][0][1]["files"]] == ["Tailan_sar.pdf"]
    assert [p.name for p in opened] == ["Tailan_sar.pdf"]
    assert [a["tool"] for a in turn["actions"]] == ["find_files", "open_file"]
    assert turn["stage"] == "final" and turn["response"] == "За, Tailan_sar.pdf-ийг нээлээ."
    assert "find_files, open_file and read_file work on its files" in planner.systems[-1]


def test_files_stay_away_when_the_api_is_not_on_the_computer(client, planner):
    planner.then(("find_files", {"user_request": "x"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "файлаа ол", "context": context()}).json()
    assert turn["actions"][0]["result"]["error_code"] == "NOT_ON_COMPUTER"
