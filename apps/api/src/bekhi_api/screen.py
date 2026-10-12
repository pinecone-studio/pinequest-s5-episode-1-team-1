"""look_at_screen: what is on the user's computer screen, explained in Mongolian ("Энэ алдаа юу гэсэн үг
вэ?", "энэ хуудсыг орчуулаад тайлбарла").

On Windows the picture is of the window the user is working in: the topmost visible window that is
not BEKHI's own (Ctrl+Space puts BEKHI in front of it), drawn even where BEKHI covers it. On a Mac it
is the whole screen. It goes to Gemini only for that one answer (providers Reader): never kept,
never logged.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Any

from . import system
from .models import ActionResult
from .providers.base import ReaderError

log = logging.getLogger(__name__)

BEKHI_WINDOW_TITLE = "BEKHI"
MIN_SIDE = 120  # smaller windows are toolbars and popups, not what the user means
MAX_WIDTH = 1600  # wider pictures are shrunk: as readable for the model, and much faster
PW_RENDERFULLCONTENT = 2  # browsers and other GPU-drawn windows
WS_EX_TOOLWINDOW = 0x80
GWL_EXSTYLE = -20
DWMWA_CLOAKED = 14  # hidden store apps and windows on other virtual desktops
DPI_PER_MONITOR_AWARE_V2 = -4


def png(width: int, height: int, bgra: bytes) -> bytes:
    """A PNG of 32-bit top-down BGRA pixels (what Windows gives), as RGB."""
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def shrink(width: int, height: int, bgra: bytes) -> tuple[int, int, bytes]:
    """Every n-th pixel and row, so the picture is at most MAX_WIDTH wide."""
    step = -(-width // MAX_WIDTH)
    if step <= 1:
        return width, height, bgra
    pixels = memoryview(bgra).cast("I")
    rows = [pixels[y * width:(y + 1) * width:step] for y in range(0, height, step)]
    return len(rows[0]), len(rows), b"".join(r.tobytes() for r in rows)


def _user_window() -> tuple[int, str] | None:
    """The topmost window the user works in: visible, not minimized, titled, not BEKHI's."""
    from ctypes import wintypes

    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        text = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, text, 256)
        title = text.value.strip()
        if not title or title in (BEKHI_WINDOW_TITLE, "Program Manager"):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left < MIN_SIDE or rect.bottom - rect.top < MIN_SIDE:
            return True
        found.append((hwnd, title))
        return False  # windows come front to back: the first one is it

    user32.EnumWindows(each, 0)
    return found[0] if found else None


def _windows_shot() -> tuple[bytes, str] | None:
    from ctypes import wintypes

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    # Real pixels on a scaled display (this thread only).
    user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(DPI_PER_MONITOR_AWARE_V2))
    window = _user_window()
    if window is None:
        return None
    hwnd, title = window
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen_dc = user32.GetDC(None)
    dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    try:
        gdi32.SelectObject(dc, bitmap)
        if not user32.PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT):
            return None
        info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(dc, bitmap, 0, height, pixels, ctypes.byref(info), 0):
            return None
        return png(*shrink(width, height, pixels.raw)), title
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, screen_dc)


def _mac_shot() -> tuple[bytes, str] | None:
    """The whole screen (needs Screen Recording for BEKHI in System Settings → Privacy & Security)."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        if subprocess.run(["screencapture", "-x", "-t", "png", path], timeout=15, check=False).returncode != 0:
            return None
        data = Path(path).read_bytes()
        return (data, "") if data else None
    finally:
        Path(path).unlink(missing_ok=True)


def capture() -> tuple[bytes, str] | None:
    """(PNG, the window's title) or None."""
    if system.IS_WINDOWS:
        return _windows_shot()
    if system.IS_MAC:
        return _mac_shot()
    return None


def _result(action_id: str, code: str | None, data: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(action_id=action_id, tool="look_at_screen", status="failed" if code else "succeeded",
                        executed_via="backend", error_code=code, data=data)


async def look_at_screen(action_id: str, args: dict[str, Any], reader: Any) -> ActionResult:
    if reader is None:
        return _result(action_id, "READER_UNAVAILABLE")
    try:
        shot = await asyncio.to_thread(capture)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("screen capture failed: %s", type(e).__name__)
        shot = None
    if shot is None:
        return _result(action_id, "SCREEN_UNAVAILABLE")
    picture, title = shot
    where = f'the window "{title}"' if title else "their screen"
    try:
        answer = await reader.read(picture, "image/png", f"The user is looking at {where} and asks: {args['question']}")
    except ReaderError as e:  # the model's quota or a network error: the turn says so, it does not fail
        log.warning("screen reading failed: %s", e)
        return _result(action_id, "READER_UNAVAILABLE")
    if not answer:
        return _result(action_id, "READER_UNAVAILABLE")
    return _result(action_id, None, {"window": title, "answer_mn": answer, "summary_mn": answer})
