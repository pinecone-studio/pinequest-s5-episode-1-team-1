"""The computer BEKHI runs on, Windows or Mac: where its data lives, how to open a file, folder,
link or app, which browser can show BEKHI's own windows, and the controls (volume, lock, typing,
media keys) in windows_controls.py or mac_controls.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def supported() -> bool:
    return IS_WINDOWS or IS_MAC


def data_dir(create: bool = True) -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    path = base / "BEKHI"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def controls() -> ModuleType:
    if IS_MAC:
        from . import mac_controls

        return mac_controls
    from . import windows_controls

    return windows_controls


def open_path(target: str | Path) -> None:
    """Opens a file, folder, app or link the way a double click does."""
    if IS_WINDOWS:
        os.startfile(target)  # type: ignore[attr-defined]  # Windows only
    else:
        subprocess.run(["open", str(target)], check=True, timeout=15)


def browsers() -> list[Path]:
    """Chromium browsers that can show BEKHI's windows in app mode (no address bar)."""
    if IS_MAC:
        roots = [Path("/Applications"), Path.home() / "Applications"]
        apps = [("Google Chrome.app", "Google Chrome"), ("Microsoft Edge.app", "Microsoft Edge")]
        return [root / app / "Contents" / "MacOS" / exe for root in roots for app, exe in apps]
    return [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
