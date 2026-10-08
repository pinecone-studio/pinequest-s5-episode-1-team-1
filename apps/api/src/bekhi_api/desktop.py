"""Actions on this Windows PC, for the web app running on it: the PC is the device.

Reminders, alarms and event reminders are Windows toast notifications. They are kept
in the API process (and in a small JSON file, so a restart does not lose them): they
fire while the BEKHI API is running, and ones missed while it was stopped fire at start.
Nothing is registered with the OS (no scheduled tasks, no autostart).

Linked with a sync code (POST /api/v1/desktop/sync), the PC is one of the user's devices: it
pulls alarms and timers set on the phone (sync.py) and rings them too, even with the browser closed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

# Toasts appear as Windows PowerShell; an unregistered app id would be dropped silently.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
CHECK_EVERY_SECONDS = 10  # wall-clock polling, so a sleeping PC still fires on wake
MISSED_GRACE = timedelta(hours=12)  # overdue at start: fire if this recent, else drop
NOTES_FILE_NAME = "БЭХИ тэмдэглэл.txt"
# The app was called Duud before: its notes and scheduled items move to the new names on first use.
OLD_NOTES_FILE_NAME = "Duud тэмдэглэл.txt"
OLD_DATA_DIR_NAME = "Duud"
CREATE_NO_WINDOW = 0x08000000
SYNC_EVERY_SECONDS = 30
# A synced alarm about to ring (or ringing) is not scheduled again: clocks differ by a few seconds.
SYNC_MIN_LEAD = timedelta(seconds=5)

TOAST_SCRIPT = """$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@'
{xml}
'@)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def available() -> bool:
    return sys.platform == "win32"


@dataclass
class Toast:
    id: str
    fire_at: str  # local wall-clock ISO, no offset
    title: str
    body: str
    alarm: bool
    kind: str = "reminder"  # reminder | alarm | event | timer
    sync_id: str | None = None  # shared with the other linked devices' copies


def _data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    d = base / "BEKHI"
    if (base / OLD_DATA_DIR_NAME).is_dir() and not d.exists():
        (base / OLD_DATA_DIR_NAME).rename(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _documents_dir() -> Path:
    """The real Documents folder (it is often redirected into OneDrive)."""
    from .windows_controls import known_folder

    try:
        return Path(known_folder("documents"))
    except OSError:
        return Path.home() / "Documents"


def toast_xml(title: str, body: str, alarm: bool) -> str:
    # The alarm scenario keeps the toast on screen and loops the alarm sound until dismissed.
    scenario = "alarm" if alarm else "reminder"
    audio = '<audio src="ms-winsoundevent:Notification.Looping.Alarm" loop="true"/>' if alarm else ""
    return (
        f'<toast scenario="{scenario}"><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text></binding></visual>{audio}"
        '<actions><action content="Хаах" arguments="dismiss" activationType="system"/></actions></toast>'
    )


async def show_toast(title: str, body: str, alarm: bool = False) -> None:
    script = TOAST_SCRIPT.format(xml=toast_xml(title, body, alarm), app_id=APP_ID)
    proc = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
        base64.b64encode(script.encode("utf-16-le")).decode(),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
    )
    _, err = await asyncio.wait_for(proc.communicate(), timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"toast failed: {err.decode(errors='replace')[:200]}")


class DesktopScheduler:
    def __init__(self, store: Path | None = None, sync: Any = None) -> None:
        self._store = store or _data_dir() / "reminders.json"
        self._link_file = self._store.with_name("sync.json")
        self._pending: list[Toast] = self._load()
        self._task: asyncio.Task | None = None
        self._sync = sync  # sync.SyncStore
        self._link: dict[str, str] | None = self._load_link()
        self._synced: set[str] = {t.sync_id for t in self._pending if t.sync_id}

    def _load_link(self) -> dict[str, str] | None:
        try:
            link = json.loads(self._link_file.read_text(encoding="utf-8"))
            return link if {"account", "device_id"} <= set(link) else None
        except (OSError, ValueError):
            return None

    def link(self, account: str) -> str:
        """Joins the PC to a sync account (the hash of the code, never the code); returns its device id."""
        device_id = (self._link or {}).get("device_id") or f"pc-{uuid.uuid4().hex[:16]}"
        self._link = {"account": account, "device_id": device_id}
        self._link_file.write_text(json.dumps(self._link), encoding="utf-8")
        return device_id

    async def sync_now(self, now: datetime | None = None) -> None:
        """Rings what the other devices set; drops what any device cancelled."""
        if self._sync is None or self._link is None:
            return
        now = now or datetime.now(timezone.utc)
        account = self._link["account"]
        await self._sync.touch_device(account, self._link["device_id"], "web", now)
        active, cancelled = await self._sync.pull(account, now)
        for a in active:
            when = datetime.fromisoformat(a["fire_at"])
            if a["id"] in self._synced or when <= now + SYNC_MIN_LEAD:
                continue
            if a["kind"] == "timer":
                self.add(when, a["title"], "Таймер дууслаа", alarm=True, kind="timer", sync_id=a["id"])
            else:
                self.add(when, a["title"], "БЭХИ сэрүүлэг", alarm=True, kind="alarm", sync_id=a["id"])
        gone = set(cancelled)
        if any(t.sync_id in gone for t in self._pending):
            self._pending = [t for t in self._pending if t.sync_id not in gone]
            self._save()

    def _load(self) -> list[Toast]:
        try:
            return [Toast(**t) for t in json.loads(self._store.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self) -> None:
        self._store.write_text(json.dumps([asdict(t) for t in self._pending], ensure_ascii=False), encoding="utf-8")

    def add(self, fire_at: datetime, title: str, body: str, alarm: bool, kind: str = "reminder",
            sync_id: str | None = None) -> None:
        local = fire_at.astimezone().replace(tzinfo=None, microsecond=0)
        self._pending.append(Toast(uuid.uuid4().hex[:12], local.isoformat(), title, body, alarm, kind, sync_id))
        if sync_id:
            self._synced.add(sync_id)
        self._save()

    def items(self) -> list[dict[str, Any]]:
        """What is still to come, soonest first; times carry this PC's UTC offset."""
        ordered = sorted(self._pending, key=lambda t: t.fire_at)
        return [
            {"id": t.id, "title": t.title, "kind": t.kind, "sync_id": t.sync_id,
             "fire_at": datetime.fromisoformat(t.fire_at).astimezone().isoformat(timespec="seconds")}
            for t in ordered
        ]

    def cancel(self, ids: set[str]) -> list[Toast]:
        """Removes the given items and returns them."""
        gone = [t for t in self._pending if t.id in ids]
        self._pending = [t for t in self._pending if t.id not in ids]
        self._save()
        return gone

    def start(self) -> None:
        now = datetime.now()
        stale = [t for t in self._pending if datetime.fromisoformat(t.fire_at) < now - MISSED_GRACE]
        if stale:
            self._pending = [t for t in self._pending if t not in stale]
            self._save()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        last_sync = 0.0
        loop = asyncio.get_running_loop()
        while True:
            if loop.time() - last_sync >= SYNC_EVERY_SECONDS:
                last_sync = loop.time()
                try:
                    await self.sync_now()
                except Exception as e:  # offline or Supabase down: try again next round
                    log.warning("alarm sync failed: %s", type(e).__name__)
            await self.fire_due(datetime.now())
            await asyncio.sleep(CHECK_EVERY_SECONDS)

    async def fire_due(self, now: datetime) -> None:
        due = [t for t in self._pending if datetime.fromisoformat(t.fire_at) <= now]
        for t in due:
            try:
                await show_toast(t.title, t.body, t.alarm)
            except Exception:
                log.exception("desktop toast failed")
            self._pending.remove(t)
            self._save()


# How people name apps -> the Start menu name. Built-in tools have no Start menu shortcut.
APP_ALIASES = {
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "chrome": "google chrome",
    "хром": "google chrome",
    "edge": "microsoft edge",
}
BUILTIN_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
}


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _start_menu_dirs() -> list[Path]:
    roots = [os.environ.get("ProgramData"), os.environ.get("APPDATA")]
    return [Path(r) / "Microsoft" / "Windows" / "Start Menu" / "Programs" for r in roots if r]


def find_app(name: str, start_menu: list[Path] | None = None) -> str | None:
    """A Start menu shortcut (or built-in tool) for the app the user named. Only apps that
    are installed and listed in the Start menu can be opened, never an arbitrary file."""
    wanted = name.strip().lower()
    wanted = APP_ALIASES.get(wanted, wanted)
    key = _norm(wanted)
    if not key:
        return None
    for builtin, exe in BUILTIN_APPS.items():
        if _norm(builtin) == key:
            return exe
    shortcuts = [
        p
        for d in (start_menu if start_menu is not None else _start_menu_dirs())
        if d.is_dir()
        for p in d.rglob("*.lnk")
        if "uninstall" not in p.stem.lower()
    ]
    for matches in (
        [p for p in shortcuts if _norm(p.stem) == key],
        [p for p in shortcuts if _norm(p.stem).startswith(key)],
        [p for p in shortcuts if key in _norm(p.stem)],
    ):
        if matches:
            return str(min(matches, key=lambda p: len(p.stem)))
    return None


def append_note(text: str, now: datetime | None = None) -> Path:
    path = _documents_dir() / NOTES_FILE_NAME
    old = path.with_name(OLD_NOTES_FILE_NAME)
    if old.exists() and not path.exists():
        old.rename(path)
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}]\n{text.strip()}\n\n")
    return path


# Minutes either side of a spoken time ("3 цагийнхаа сануулга") that still count as that reminder.
MATCH_WINDOW = timedelta(minutes=15)
VOLUME_STEP = 10  # percentage points per "дууг нэм/багасга"


def pick_scheduled(items: list[dict[str, Any]], args: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """The items cancel_reminder means, and whether the request is ambiguous (several, no filter)."""
    if args.get("all"):
        return items, False
    query = _norm(args.get("query") or "")
    at = datetime.fromisoformat(args["at"]) if args.get("at") else None
    if not query and at is None:
        return items, len(items) > 1
    return [
        i
        for i in items
        if (not query or query in _norm(i["title"]))
        and (at is None or abs(datetime.fromisoformat(i["fire_at"]) - at) <= MATCH_WINDOW)
    ], False


def _result(status: str, error_code: str | None = None, data: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "executed_via": "backend", "error_code": error_code, "data": data, **extra}


def computer_control(args: dict[str, Any]) -> dict[str, Any]:
    from . import windows_controls as win

    action = args["action"]
    if action == "lock_screen":
        return _result("succeeded") if win.lock_screen() else _result("failed", "LOCK_FAILED")
    if action == "open_folder":
        os.startfile(win.known_folder(args.get("folder") or "downloads"))
        return _result("succeeded")
    if action == "set_volume" and args.get("level") is None:
        return _result("failed", "INVALID_ARGUMENTS")
    change = {
        "volume_up": {"delta": VOLUME_STEP},
        "volume_down": {"delta": -VOLUME_STEP},
        "set_volume": {"level": args.get("level")},
        "mute": {"mute": True},
        "unmute": {"mute": False},
    }[action]
    try:
        level = win.change_volume(**change)
    except OSError:
        return _result("failed", "VOLUME_UNAVAILABLE")
    return _result("succeeded", data={"volume": level})


def run(tool: str, args: dict[str, Any], scheduler: DesktopScheduler) -> dict[str, Any]:
    """Returns {status, executed_via, error_code, data}; the API wraps it as an ActionResult."""

    def at(key: str) -> datetime | None:
        when = datetime.fromisoformat(args[key])
        return when if when > datetime.now(when.tzinfo) else None

    if tool == "create_note":
        title = args.get("title")
        append_note(f"{title}\n{args['body']}" if title else args["body"])
        return _result("succeeded")
    if tool == "open_app":
        target = find_app(args["app_name"])
        if target is None:
            return _result("failed", "APP_NOT_FOUND")
        os.startfile(target)
        return _result("succeeded")
    if tool == "set_timer":
        # The backend sets fire_at from its clock, so all linked devices ring together.
        when = (
            datetime.fromisoformat(args["fire_at"]) if args.get("fire_at")
            else datetime.now().astimezone() + timedelta(seconds=int(args["duration_seconds"]))
        )
        # The title names it in lists ("Таймер"); the toast's second line says it has run out.
        scheduler.add(when, args.get("label") or "Таймер", "Таймер дууслаа", alarm=True, kind="timer",
                      sync_id=args.get("sync_id"))
        return _result("succeeded")
    if tool == "list_reminders":
        return _result("succeeded", data={"items": scheduler.items()[:10]})
    if tool == "cancel_reminder":
        matches, ambiguous = pick_scheduled(scheduler.items(), args)
        if ambiguous:
            return _result("needs_clarification", "REMINDER_AMBIGUOUS", match_count=len(matches))
        if not matches:
            return _result("failed", "REMINDER_NOT_FOUND")
        gone = scheduler.cancel({i["id"] for i in matches})
        # The app cancels the synced ones on the server too, so the other devices drop them.
        return _result("succeeded", data={
            "cancelled": [t.title for t in gone],
            "cancelled_sync_ids": [t.sync_id for t in gone if t.sync_id],
        })
    if tool == "computer_control":
        return computer_control(args)
    fields = {
        "create_reminder": ("due_at", "reminder", lambda: (args["title"], args.get("notes") or "БЭХИ сануулга", False)),
        "create_alarm": ("fire_at", "alarm", lambda: (args.get("label") or "Сэрэх цаг боллоо", "БЭХИ сэрүүлэг", True)),
        "create_calendar_event": ("start_at", "event", lambda: (args["title"], args.get("location") or "БЭХИ: эхлэх цаг боллоо", False)),
    }
    if tool not in fields:
        return _result("unsupported", "DESKTOP_UNSUPPORTED") | {"executed_via": None}
    key, kind, content = fields[tool]
    when = at(key)
    if when is None:
        return _result("failed", "TIME_IN_PAST")
    title, body, alarm = content()
    scheduler.add(when, title, body, alarm, kind, sync_id=args.get("sync_id") if tool == "create_alarm" else None)
    return _result("succeeded")
