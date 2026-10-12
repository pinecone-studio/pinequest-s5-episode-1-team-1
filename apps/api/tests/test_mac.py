"""BEKHI on a Mac: apps, settings pages, volume, typing, media and notifications through macOS's own
tools. macOS's commands (osascript, pbcopy, open) are faked, so this runs on any computer."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from bekhi_api import desktop, mac_controls, pc_files, system


class FakeMac:
    """subprocess.run for osascript, pbcopy, pbpaste, pmset and afplay."""

    def __init__(self, front: str = "Notes", running: tuple[str, ...] = ("Spotify",)):
        self.calls: list[list[str]] = []
        self.scripts: list[str] = []
        self.volume, self.muted = 50, False
        self.clipboard = b"copied before"
        self.front, self.running = front, running
        self.no_accessibility = False

    def __call__(self, args, input=None, capture_output=False, text=False, timeout=None, check=False):
        self.calls.append(list(args))
        out, code = "", 0
        if args[0] == "osascript":
            script = args[2]
            self.scripts.append(script)
            if script == "get volume settings":
                out = f"output volume:{self.volume}, input volume:75, alert volume:100, output muted:{str(self.muted).lower()}"
            elif script.startswith("set volume output volume"):
                self.volume = int(script.split()[4])
            elif script.startswith("set volume output muted"):
                self.muted = script.endswith("true")
            elif script.endswith("is running"):
                out = "true" if any(f'"{app}"' in script for app in self.running) else "false"
            elif "title of front window" in script:
                out = self.front
            elif "keystroke" in script and self.no_accessibility:
                code = 1
        elif args[0] == "pbpaste":
            out = self.clipboard
        elif args[0] == "pbcopy":
            self.clipboard = input
        if isinstance(out, str) and not text:
            out = out.encode()
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="" if text else b"")


@pytest.fixture
def mac(monkeypatch):
    fake = FakeMac()
    monkeypatch.setattr(system, "IS_MAC", True)
    monkeypatch.setattr(system, "IS_WINDOWS", False)
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(mac_controls.time, "sleep", lambda s: None)
    return fake


def test_apps_are_found_in_applications_and_settings_open_system_settings(mac, tmp_path):
    apps = tmp_path / "Applications"
    for bundle in ("Visual Studio Code.app", "Google Chrome.app", "Utilities/Terminal.app",
                   "Adobe Photoshop 2025/Adobe Photoshop 2025.app"):
        (apps / bundle / "Contents").mkdir(parents=True)
    assert desktop.find_app("VS Code", [apps]).endswith("Visual Studio Code.app")
    assert desktop.find_app("Хром", [apps]).endswith("Google Chrome.app")
    assert desktop.find_app("Terminal", [apps]).endswith("Terminal.app")
    assert desktop.find_app("Photoshop", [apps]).endswith("Adobe Photoshop 2025.app")
    assert desktop.find_app("Calculator", [apps]) == "/System/Applications/Calculator.app"
    assert desktop.find_app("Wi-Fi тохиргоо", [apps]) == "x-apple.systempreferences:com.apple.wifi-settings-extension"
    assert desktop.find_app("Spotify", [apps]) is None


def test_open_app_folder_and_link_use_open(mac, tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "find_app", lambda name: "/Applications/Spotify.app")
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("open_app", {"app_name": "Spotify"}, s)["status"] == "succeeded"
    assert desktop.run("open_url", {"url": "https://www.youtube.com/"}, s)["status"] == "handed_off"
    assert desktop.run("computer_control", {"action": "open_folder", "folder": "videos"}, s)["status"] == "succeeded"
    assert [c for c in mac.calls if c[0] == "open"] == [
        ["open", "/Applications/Spotify.app"], ["open", "https://www.youtube.com/"], ["open", str(Path.home() / "Movies")],
    ]


def test_volume(mac, tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("computer_control", {"action": "volume_up"}, s)["data"] == {"volume": 60}
    assert desktop.run("computer_control", {"action": "set_volume", "level": 130}, s)["data"] == {"volume": 100}
    desktop.run("computer_control", {"action": "mute"}, s)
    assert mac.muted and mac.volume == 100
    assert mac_controls.parse_volume("output volume:missing value, output muted:missing value") == (0, False)


def test_typing_pastes_the_text_and_gives_the_clipboard_back(mac, tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("type_text", {"text": "Маргааш уулзъя."}, s)["status"] == "succeeded"
    assert ['tell application "System Events" to keystroke "v" using command down'] == [
        x for x in mac.scripts if "keystroke" in x]
    assert ["pbcopy", "Маргааш уулзъя.".encode()] not in mac.calls  # sent on stdin, not as an argument
    assert mac.clipboard == b"copied before"

    # Said to BEKHI's own window: ⌘Tab back to the app the user was in first.
    mac.front, mac.scripts = "BEKHI", []
    desktop.run("type_text", {"text": "Сайн уу"}, s)
    assert [x for x in mac.scripts if "keystroke" in x] == [
        'tell application "System Events" to keystroke tab using command down',
        'tell application "System Events" to keystroke "v" using command down',
    ]

    mac.no_accessibility = True  # BEKHI not allowed in Privacy & Security → Accessibility
    assert desktop.run("type_text", {"text": "x"}, s)["error_code"] == "TYPING_FAILED"


def test_media_keys_control_the_music_app_that_is_open(mac, tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("computer_control", {"action": "media_next"}, s)["status"] == "succeeded"
    assert 'tell application "Spotify" to next track' in mac.scripts
    assert not any(x.startswith('tell application "Music"') for x in mac.scripts)
    mac.running = ()
    assert desktop.run("computer_control", {"action": "media_play_pause"}, s)["error_code"] == "MEDIA_KEY_FAILED"


def test_lock_screen_falls_back_to_display_sleep(mac, tmp_path):
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("computer_control", {"action": "lock_screen"}, s)["status"] == "succeeded"
    assert ["pmset", "displaysleepnow"] not in mac.calls
    mac.no_accessibility = True
    assert desktop.run("computer_control", {"action": "lock_screen"}, s)["status"] == "succeeded"
    assert ["pmset", "displaysleepnow"] in mac.calls


def test_reminders_are_mac_notifications_and_alarms_ring(mac):
    asyncio.run(desktop.show_toast('Ус "уух"', "БЭХИ сануулга"))
    assert mac.scripts[-1] == 'display notification "БЭХИ сануулга" with title "Ус \\"уух\\"" sound name "Glass"'
    asyncio.run(desktop.show_toast("Сэрэх цаг боллоо", "БЭХИ сэрүүлэг", alarm=True))
    assert sum(c[0] == "afplay" for c in mac.calls) == 3


def test_windows_open_in_chrome_or_edge_and_data_lives_in_application_support(mac, monkeypatch, tmp_path):
    assert str(system.browsers()[0]).replace("\\", "/") == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert system.data_dir() == tmp_path / "Library" / "Application Support" / "BEKHI"
    assert system.data_dir().is_dir()


def test_photos_library_is_not_searched(tmp_path, monkeypatch):
    pictures = tmp_path / "Pictures"
    (pictures / "Photos Library.photoslibrary" / "originals").mkdir(parents=True)
    (pictures / "Photos Library.photoslibrary" / "originals" / "IMG_0001.jpg").write_bytes(b"x")
    (pictures / "Аялал.jpg").write_bytes(b"x")
    monkeypatch.setattr(pc_files, "_folder_path", lambda f: pictures if f == "pictures" else tmp_path / "none")
    found = pc_files.find_files("a", {"kind": "image"}).data["files"]
    assert [f["name"] for f in found] == ["Аялал.jpg"]
