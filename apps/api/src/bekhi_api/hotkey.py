"""Ctrl+Space anywhere on the computer: BEKHI's window comes to the front and starts listening, as if
its orb were pressed. Windows only (RegisterHotKey). Nothing is installed in the system: the key
works while BEKHI's API runs on this computer. The web app hears of each press by waiting on
GET /api/v1/desktop/wake (Wakeups).

While BEKHI runs, Ctrl+Space is BEKHI's in every program (VS Code's suggestions and the input
language switch use it too): the user chose it. When a program already has it, the next free key in
KEYS is taken.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_SPACE = 0x20
KEYS = [("Ctrl+Space", MOD_CONTROL), ("Alt+Space", MOD_ALT), ("Ctrl+Alt+Space", MOD_CONTROL | MOD_ALT)]
REGISTER_WAIT_SECONDS = 2
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
SW_RESTORE = 9
HOTKEY_ID = 0xBE41


class Wakeups:
    """Counts presses of the key; the web app waits for the count to pass the last one it saw."""

    def __init__(self) -> None:
        self.count = 0
        self._changed = asyncio.Condition()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def press(self) -> None:
        """Called from the key's thread."""
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._bump(), self._loop)

    async def _bump(self) -> None:
        async with self._changed:
            self.count += 1
            self._changed.notify_all()

    async def after(self, seen: int, wait: float) -> int:
        """The press count once it is above `seen`, or as it is after `wait` seconds."""
        async with self._changed:
            try:
                await asyncio.wait_for(self._changed.wait_for(lambda: self.count > seen), wait)
            except TimeoutError:
                pass
            return self.count


def bring_to_front(title: str) -> bool:
    """Shows the window with this exact title (BEKHI's own window) in front, restored if minimized."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, text, 256)
            if text.value == title:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(each, 0)
    if not found:
        return False
    if user32.IsIconic(found[0]):
        user32.ShowWindow(found[0], SW_RESTORE)
    # Allowed: this process has just received the key press.
    return bool(user32.SetForegroundWindow(found[0]))


class Hotkey:
    """The key, registered on a thread of its own that waits for presses."""

    def __init__(self, on_press: Callable[[], None]) -> None:
        self._on_press = on_press
        self._thread_id: int | None = None
        self._registered = threading.Event()
        self.label: str | None = None  # the key taken, once registered

    def start(self) -> None:
        threading.Thread(target=self._run, name="bekhi-hotkey", daemon=True).start()
        self._registered.wait(REGISTER_WAIT_SECONDS)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = threading.get_native_id()
        # The key belongs to the thread that registers it: its presses arrive in this thread's queue.
        self.label = next((label for label, mods in KEYS
                           if user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, VK_SPACE)), None)
        self._registered.set()
        if self.label is None:
            log.warning("no key to call BEKHI: %s are all taken by other programs", ", ".join(k for k, _ in KEYS))
            self._thread_id = None
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self._on_press()
                    except Exception:
                        log.exception("hotkey press failed")
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
