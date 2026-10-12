"""BEKHI as an app on the computer: one click on the desktop shortcut (install-desktop.ps1) or on
BEKHI in a Mac's Applications (install-desktop.sh) starts this API on the computer and opens BEKHI
in its own window, Edge or Chrome in app mode with no browser bar. The API serves that window (the
web app built into apps/api/web), talks to the speech and language providers with the keys in
apps/api/.env, and does the computer's own actions: apps, volume, typing, reminders as
notifications. Phones on the same Wi-Fi can use it too. Closing the window stops BEKHI.

    pythonw bekhi_desktop.pyw    (what the Windows shortcut runs: no console window)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from . import config, system
from .desktop import browser

PORT = 8000  # the web app finds the API on the port it was served from
URL = f"http://127.0.0.1:{PORT}/"


def _running() -> bool:
    """A BEKHI API already answers here (BEKHI was opened twice): just open another window."""
    try:
        with urllib.request.urlopen(URL + "api/v1/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _open_window() -> subprocess.Popen | None:
    exe = browser()
    if exe is None:
        webbrowser.open(URL)
        return None
    # Its own profile: a separate browser process (it ends when the window closes) that keeps the
    # microphone permission and this window's sync code.
    return subprocess.Popen([
        str(exe), f"--app={URL}", f"--user-data-dir={system.data_dir() / 'window'}",
        "--window-size=460,900", "--no-first-run", "--no-default-browser-check",
        # Called up with Ctrl+Space (hotkey.py), it listens and speaks before anyone clicks in it.
        "--autoplay-policy=no-user-gesture-required",
    ])


def main() -> None:
    # Started from a shortcut or the Dock (pythonw has no console; a Mac app's output goes nowhere):
    # the log goes to a file.
    if sys.stdout is None or sys.stderr is None or not sys.stderr.isatty():
        log = open(system.data_dir() / "bekhi.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stderr = log
    if _running():
        _open_window()
        return

    # Same settings as the PC agent (agent.py), plus the window, and phones on the Wi-Fi may connect.
    os.environ.setdefault("DESKTOP_ACTIONS", "true")
    os.environ.setdefault("SYNC_API_URL", "https://bekhi-api.onrender.com")
    os.environ.setdefault("WEB_DIR", str(config.API_ROOT / "web"))
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("bekhi_api.main:app", host="0.0.0.0", port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started or not thread.is_alive():
            break
        time.sleep(0.1)
    if not server.started:
        print("BEKHI could not start (is port 8000 in use?)", file=sys.stderr)
        return
    window = _open_window()
    if window is None:  # no Edge or Chrome: the normal browser, and BEKHI runs until signed out
        thread.join()
        return
    window.wait()
    server.should_exit = True
    thread.join(timeout=10)


if __name__ == "__main__":
    main()
