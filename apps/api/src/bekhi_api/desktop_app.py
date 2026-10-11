"""BEKHI as an app on the computer: one click on the desktop shortcut (install-desktop.ps1) starts
this API on the PC and opens BEKHI in its own window, Microsoft Edge in app mode with no browser bar.
The API serves that window (the web app built into apps/api/web), talks to the speech and language
providers with the keys in apps/api/.env, and does the PC's own actions: apps, volume, typing,
reminders as toasts. Phones on the same Wi-Fi can use it too. Closing the window stops BEKHI.

    pythonw bekhi_desktop.pyw    (what the shortcut runs: no console window)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import config
from .desktop import EDGE_PATHS

PORT = 8000  # the web app finds the API on the port it was served from
URL = f"http://127.0.0.1:{PORT}/"


def _data_dir() -> Path:
    path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BEKHI"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _running() -> bool:
    """A BEKHI API already answers here (BEKHI was opened twice): just open another window."""
    try:
        with urllib.request.urlopen(URL + "api/v1/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _open_window() -> subprocess.Popen | None:
    browser = next((p for p in EDGE_PATHS if p.is_file()), None)
    if browser is None:
        webbrowser.open(URL)
        return None
    # Its own profile: a separate browser process (it ends when the window closes) that keeps the
    # microphone permission and this window's sync code.
    return subprocess.Popen([
        str(browser), f"--app={URL}", f"--user-data-dir={_data_dir() / 'window'}",
        "--window-size=460,900", "--no-first-run", "--no-default-browser-check",
    ])


def main() -> None:
    if sys.stdout is None or sys.stderr is None:  # pythonw: no console, so the log goes to a file
        log = open(_data_dir() / "bekhi.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
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
