"""Mac controls for desktop actions, the same functions as windows_controls.py: volume, lock screen,
standard folders, typing, media and notifications, through macOS's own tools (osascript, pmset,
pbcopy). Typing and switching windows need BEKHI's Python to be allowed in System Settings →
Privacy & Security → Accessibility; macOS asks the first time."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

FOLDERS = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Movies",
}
MEDIA_KEYS = {"media_play_pause": "playpause", "media_next": "next track", "media_previous": "previous track"}
PLAYERS = ("Spotify", "Music")  # apps that take AppleScript play commands
BEKHI_WINDOW_TITLE = "BEKHI"


def osascript(script: str, timeout: float = 10) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


def _quote(text: str) -> str:
    """A string literal for AppleScript."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_volume(settings: str) -> tuple[int, bool]:
    """"output volume:50, input volume:75, alert volume:100, output muted:false" -> (50, False)."""
    level = re.search(r"output volume:(\d+)", settings)
    muted = re.search(r"output muted:(true|false)", settings)
    return (int(level.group(1)) if level else 0), bool(muted and muted.group(1) == "true")


def get_volume() -> tuple[int, bool]:
    return parse_volume(osascript("get volume settings"))


def change_volume(*, delta: int | None = None, level: int | None = None, mute: bool | None = None) -> int:
    current, _ = get_volume()
    if mute is not None:
        osascript(f"set volume output muted {'true' if mute else 'false'}")
        return current
    target = max(0, min(100, level if level is not None else current + (delta or 0)))
    osascript(f"set volume output volume {target} without output muted")
    return target


def lock_screen() -> bool:
    """⌃⌘Q, the Mac's own Lock Screen; without Accessibility, the display sleeps instead, which locks
    the Mac when it asks for the password after sleep (the default)."""
    try:
        osascript('tell application "System Events" to keystroke "q" using {control down, command down}')
        return True
    except (OSError, subprocess.SubprocessError):
        return subprocess.run(["pmset", "displaysleepnow"], timeout=10, check=False).returncode == 0


def known_folder(name: str) -> str:
    return str(Path.home() / FOLDERS[name])


def _front_window_title() -> str:
    try:
        return osascript('tell application "System Events" to get title of front window of '
                         "(first application process whose frontmost is true)")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def type_text(text: str) -> bool:
    """Types `text` where the cursor is: through the clipboard and ⌘V, which keeps any script (Cyrillic)
    intact. The clipboard is put back afterwards."""
    try:
        previous = subprocess.run(["pbpaste"], capture_output=True, timeout=5, check=False).stdout
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
        try:
            if _front_window_title() == BEKHI_WINDOW_TITLE:
                # Said to BEKHI's own window: type into the app the user was in before (⌘Tab).
                osascript('tell application "System Events" to keystroke tab using command down')
                time.sleep(0.4)
            osascript('tell application "System Events" to keystroke "v" using command down')
            time.sleep(0.3)
        finally:
            if previous:  # text the user had copied (a copied picture cannot be put back this way)
                subprocess.run(["pbcopy"], input=previous, timeout=5, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def press_media_key(action: str) -> bool:
    """Play/pause, next or previous in Spotify or Music, whichever is open. (A Mac's media keys cannot
    be pressed from a script, so a video in a browser is not controlled.)"""
    command = MEDIA_KEYS[action]
    done = False
    for app in PLAYERS:
        try:
            if osascript(f'application "{app}" is running') == "true":
                osascript(f'tell application "{app}" to {command}')
                done = True
        except (OSError, subprocess.SubprocessError):
            continue
    return done


def notify(title: str, body: str, alarm: bool = False) -> None:
    """A notification in the corner; an alarm also rings a few times."""
    osascript(f"display notification {_quote(body)} with title {_quote(title)} sound name \"Glass\"")
    if alarm:
        for _ in range(3):
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=10, check=False)
