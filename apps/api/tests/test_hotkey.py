"""Ctrl+Space (hotkey.py): each press wakes BEKHI's window, which waits on GET /api/v1/desktop/wake."""

from __future__ import annotations

import asyncio
import threading

from bekhi_api import hotkey
from bekhi_api import main as main_mod


async def test_a_press_from_the_keys_thread_reaches_the_waiting_window():
    wakeups = hotkey.Wakeups()
    wakeups.bind(asyncio.get_running_loop())
    assert await wakeups.after(-1, 5) == 0  # the window's first call: the count as it is
    waiting = asyncio.create_task(wakeups.after(0, 5))
    await asyncio.sleep(0.05)
    threading.Thread(target=wakeups.press).start()
    assert await asyncio.wait_for(waiting, 2) == 1
    assert await wakeups.after(1, 0.05) == 1  # nothing new: answered after the wait


def test_only_the_window_on_this_computer_may_wait(client, monkeypatch):
    assert client.get("/api/v1/desktop/wake").status_code == 404  # no desktop actions here

    class ThisPc:
        async def stop(self):
            pass

    client.app.state.desktop = ThisPc()
    monkeypatch.setattr(main_mod, "_is_local", lambda request: True)
    assert client.get("/api/v1/desktop/wake?after=-1").json() == {"count": 0, "key": None}
    monkeypatch.setattr(main_mod, "_is_local", lambda request: False)
    assert client.get("/api/v1/desktop/wake?after=-1").status_code == 404
