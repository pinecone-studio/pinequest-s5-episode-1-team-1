"""Commands between the user's linked devices (packages/contracts sync.ts): say it to the phone and
the computer does it, or the other way round.

The sender posts a command for a kind of device (computer or phone) and waits for its outcome.
The target long-polls for its commands, runs each one as its own action and reports back. They
are kept in this process only: a command lives a minute at most, so nothing is worth storing.
A command nobody took in time is dropped, never run later by surprise.

When this API runs on the user's PC (agent.py) and the device asked for is not listening here,
the command goes on to the cloud API (RemoteCommands), where the phone is listening.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

TARGETS = ("computer", "phone")
RELAYED_TOOLS = {
    "computer": {"open_app", "open_url", "computer_control", "type_text", "create_note", "play_video"},
    "phone": {"call_contact", "send_message", "open_app", "open_url", "play_video"},
}
TAKE_WAIT_MAX = 25  # seconds a device waits for commands per request
STATE_WAIT_MAX = 20  # seconds a sender waits for the outcome per request
# A device long-polling (25 s at a time) counts as listening for this long after it last asked.
LISTENING_WINDOW = timedelta(seconds=40)
PENDING_TTL = timedelta(seconds=30)  # nobody took it by then: dropped
RUNNING_TTL = timedelta(seconds=60)  # taken but no outcome by then: given up


def _now() -> datetime:
    return datetime.now(timezone.utc)


def platform_of(device_id: str) -> str:
    """Device ids start with the platform ("ios-…", "android-…", "web-…"); the PC's own is "pc-…"."""
    prefix = device_id.split("-", 1)[0]
    return prefix if prefix in ("ios", "android") else "web"


@dataclass
class Command:
    id: str
    account: str
    target: str
    tool: str
    arguments: dict[str, Any]
    sender: str
    created: datetime
    state: str = "pending"  # pending -> taken -> done, or expired
    taken: datetime | None = None
    outcome: dict[str, Any] | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    def wire(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "arguments": self.arguments, "from": platform_of(self.sender)}


class CommandStore:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._listening: dict[tuple[str, str], datetime] = {}
        self._arrived: dict[tuple[str, str], asyncio.Event] = {}

    def listening(self, account: str, target: str, now: datetime | None = None) -> bool:
        seen = self._listening.get((account, target))
        return seen is not None and (now or _now()) - seen <= LISTENING_WINDOW

    def _expire(self, now: datetime) -> None:
        for c in list(self._commands.values()):
            stale = (c.state == "pending" and now - c.created > PENDING_TTL) or (
                c.state == "taken" and c.taken is not None and now - c.taken > RUNNING_TTL
            )
            if stale:
                c.state = "expired"
                c.finished.set()
            if c.state in ("done", "expired") and now - c.created > RUNNING_TTL * 2:
                del self._commands[c.id]

    def send(self, account: str, sender: str, target: str, tool: str, arguments: dict[str, Any]) -> Command | None:
        """The new command, or None when no device of that kind is listening for this account."""
        now = _now()
        self._expire(now)
        if not self.listening(account, target, now):
            return None
        cmd = Command(str(uuid.uuid4()), account, target, tool, arguments, sender, now)
        self._commands[cmd.id] = cmd
        self._arrived.setdefault((account, target), asyncio.Event()).set()
        return cmd

    async def take(self, account: str, target: str, wait: float) -> list[Command]:
        """This account's commands for that kind of device, waiting up to `wait` seconds for one."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, min(wait, TAKE_WAIT_MAX))
        key = (account, target)
        while True:
            now = _now()
            self._listening[key] = now
            self._expire(now)
            arrived = self._arrived.setdefault(key, asyncio.Event())
            arrived.clear()
            found = [c for c in self._commands.values() if c.account == account and c.target == target and c.state == "pending"]
            remaining = deadline - loop.time()
            if found or remaining <= 0:
                for c in found:
                    c.state, c.taken = "taken", now
                self._listening[key] = _now()
                return found
            try:
                await asyncio.wait_for(arrived.wait(), remaining)
            except TimeoutError:
                pass

    def finish(self, account: str, command_id: str, outcome: dict[str, Any]) -> bool:
        cmd = self._commands.get(command_id)
        if cmd is None or cmd.account != account or cmd.state != "taken":
            return False
        cmd.state, cmd.outcome = "done", outcome
        cmd.finished.set()
        return True

    async def state(self, account: str, command_id: str, wait: float) -> Command | None:
        """The command, once it is done or expired, or as it is after `wait` seconds."""
        cmd = self._commands.get(command_id)
        if cmd is None or cmd.account != account:
            return None
        if cmd.state not in ("done", "expired"):
            try:
                await asyncio.wait_for(cmd.finished.wait(), max(0.0, min(wait, STATE_WAIT_MAX)))
            except TimeoutError:
                self._expire(_now())
        return cmd


class RemoteCommands:
    """The same endpoints on another BEKHI API (the cloud's), for this API on the user's PC:
    `code` is the sync code itself, which the cloud hashes."""

    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/") + "/api/v1/sync/commands"
        self._http = http

    async def _call(self, method: str, path: str, code: str, device: str, timeout: float = 10, **kw: Any) -> Any:
        r = await self._http.request(method, self._base + path, headers={"X-Bekhi-Sync": code, "X-Bekhi-Device": device},
                                     timeout=timeout, **kw)
        r.raise_for_status()
        return r.json()

    async def send(self, code: str, device: str, target: str, tool: str, arguments: dict[str, Any]) -> str | None:
        body = await self._call("POST", "", code, device, json={"target": target, "tool": tool, "arguments": arguments})
        return body.get("id")

    async def state(self, code: str, device: str, command_id: str, wait: float) -> dict[str, Any]:
        return await self._call("GET", f"/{command_id}", code, device, timeout=wait + 10, params={"wait": wait})

    async def take(self, code: str, device: str, target: str, wait: float) -> list[dict[str, Any]]:
        body = await self._call("GET", "", code, device, timeout=wait + 10, params={"target": target, "wait": wait})
        return list(body.get("commands") or [])

    async def finish(self, code: str, device: str, command_id: str, outcome: dict[str, Any]) -> None:
        await self._call("POST", f"/{command_id}/result", code, device, json=outcome)
