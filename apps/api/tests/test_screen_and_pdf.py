"""look_at_screen and PDFs: a picture of the user's window, or their PDF, read by Gemini in Mongolian.
The capture and Gemini are faked."""

from __future__ import annotations

import struct
import zlib

from bekhi_api import main as main_mod
from bekhi_api import pc_files, screen

from .conftest import context
from .test_agent_tools import folders  # noqa: F401  (fixture)


class FakeReader:
    def __init__(self, answer="Энэ алдаа нь файл олдсонгүй гэсэн үг. Замаа шалгаарай."):
        self.answer = answer
        self.calls: list[tuple[str, str, int]] = []

    async def read(self, data: bytes, mime_type: str, instruction: str) -> str:
        self.calls.append((mime_type, instruction, len(data)))
        return self.answer


def test_the_picture_is_a_png_of_the_window():
    bgra = bytes([10, 20, 30, 0, 40, 50, 60, 0])  # two pixels, blue-green-red
    data = screen.png(2, 1, bgra)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (2, 1)
    idat = data.index(b"IDAT")
    raw = zlib.decompress(data[idat + 4:idat + 4 + struct.unpack(">I", data[idat - 4:idat])[0]])
    assert raw == bytes([0, 30, 20, 10, 60, 50, 40])  # filter byte, then red-green-blue


def test_a_wide_window_is_shrunk():
    width = screen.MAX_WIDTH * 2 + 2  # 3 times too wide at most: every 3rd pixel
    bgra = b"".join(i.to_bytes(4, "little") for i in range(width)) * 3
    w, h, small = screen.shrink(width, 3, bgra)
    assert (w, h) == (-(-width // 3), 1) and small[:8] == (0).to_bytes(4, "little") + (3).to_bytes(4, "little")
    assert screen.shrink(10, 1, b"x" * 40) == (10, 1, b"x" * 40)


async def test_looking_at_the_screen(monkeypatch):
    reader = FakeReader()
    monkeypatch.setattr(screen, "capture", lambda: (b"png-bytes", "Visual Studio Code"))
    r = await screen.look_at_screen("a", {"question": "Энэ алдаа юу гэсэн үг вэ?"}, reader)
    assert r.status == "succeeded" and r.data["answer_mn"] == reader.answer and r.data["window"] == "Visual Studio Code"
    mime, instruction, _ = reader.calls[0]
    assert mime == "image/png" and "Visual Studio Code" in instruction and "Энэ алдаа юу гэсэн үг вэ?" in instruction

    monkeypatch.setattr(screen, "capture", lambda: None)  # only BEKHI's window, or all minimized
    assert (await screen.look_at_screen("a", {"question": "x"}, reader)).error_code == "SCREEN_UNAVAILABLE"
    assert (await screen.look_at_screen("a", {"question": "x"}, None)).error_code == "READER_UNAVAILABLE"


def test_the_screen_is_looked_at_only_on_the_computer_that_runs_bekhi(client, planner, monkeypatch):
    planner.then(("look_at_screen", {"user_request": "x", "question": "Энэ юу вэ?"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Энэ юу вэ?", "context": context()}).json()
    assert turn["actions"][0]["result"]["error_code"] == "NOT_ON_COMPUTER"

    class ThisPc:
        async def stop(self):
            pass

    reader = FakeReader("Энэ хуудсанд цаг агаарын мэдээ байна.")
    client.app.state.desktop = ThisPc()
    monkeypatch.setattr(main_mod, "get_reader", lambda: reader)
    monkeypatch.setattr(screen, "capture", lambda: (b"png", "Weather - Google Chrome"))
    planner.then(("look_at_screen", {"user_request": "x", "question": "Энэ хуудсыг орчуулаад тайлбарла"}))
    planner.after_tools(("reply", {"user_request": "x", "text": "Энэ хуудсанд цаг агаарын мэдээ байна."}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Энэ хуудсыг орчуулаад тайлбарла",
                                                       "context": context(platform="web")}).json()
    assert turn["response"] == "Энэ хуудсанд цаг агаарын мэдээ байна."
    assert planner.followups[-1][0][1]["answer_mn"] == reader.answer
    assert "look_at_screen sees what is on its screen" in planner.systems[-1]


async def test_a_pdf_is_read_by_gemini_with_the_users_question(folders, monkeypatch):  # noqa: F811
    reader = FakeReader("Гэрээ 2026 оны 12 сард дуусна. Сард 500 мянга төлнө.")
    found = pc_files.find_files("a", {"kind": "pdf"}).data["files"]
    assert pc_files.is_pdf(found[0]["id"]) and not pc_files.is_pdf("f9999")
    r = await pc_files.read_pdf("r", {"file": found[0]["id"], "question": "төлбөрийн нөхцөл юу вэ?"}, reader)
    assert r.status == "succeeded" and r.data["answer_mn"] == reader.answer and r.data["name"] == "Tailan_sar.pdf"
    mime, instruction, size = reader.calls[0]
    assert mime == "application/pdf" and "төлбөрийн нөхцөл юу вэ?" in instruction and size > 0

    await pc_files.read_pdf("r", {"file": found[0]["id"]}, reader)
    assert pc_files.PDF_QUESTION in reader.calls[1][1]  # no question: its main points
    monkeypatch.setattr(pc_files, "MAX_PDF_BYTES", 1)
    assert (await pc_files.read_pdf("r", {"file": found[0]["id"]}, reader)).error_code == "FILE_TOO_LARGE"
    assert (await pc_files.read_pdf("r", {"file": found[0]["id"]}, None)).error_code == "READER_UNAVAILABLE"
