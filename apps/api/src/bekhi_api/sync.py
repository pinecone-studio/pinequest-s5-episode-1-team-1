"""Alarms and timers shared by every device linked with one sync code.

A device that sets an alarm or timer (target "all") schedules its own copy, then publishes it
here. The other devices pull the list (the phone when BEKHI is open, the Windows PC from the
API's own loop) and schedule their copies ahead of time, so they ring even without network
at that moment. Cancelling marks the alarm cancelled and every device drops its copy.

Accounts are the SHA-256 of the sync code: the code itself is never stored. Supabase holds
the data when SUPABASE_URL is set (supabase/migrations); otherwise it lives in this process,
which is enough while all devices talk to the same API.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

SYNC_CODE_LENGTH = 12
SYNC_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
DEVICE_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# A device not seen for this long is no longer counted as "also gets it" in replies.
ACTIVE_DEVICE_WINDOW = timedelta(days=30)


def account_key(code: str | None) -> str | None:
    """The account a sync code stands for, or None if it is not a well-formed code.
    Typed codes are forgiving: case, dashes and spaces are ignored, O/I/L read as 0/1/1."""
    if not code:
        return None
    norm = code.upper().translate(str.maketrans("OIL", "011")).replace("-", "").replace(" ", "")
    if len(norm) != SYNC_CODE_LENGTH or any(c not in SYNC_CODE_ALPHABET for c in norm):
        return None
    return hashlib.sha256(norm.encode()).hexdigest()


def valid_device_id(device_id: str | None) -> bool:
    return bool(device_id and DEVICE_ID.match(device_id))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class SyncStore(Protocol):
    async def touch_device(self, account: str, device_id: str, platform: str, now: datetime) -> None: ...
    async def other_devices(self, account: str, device_id: str, now: datetime) -> list[str]: ...
    async def publish(self, account: str, device_id: str, alarm: dict[str, Any]) -> None: ...
    async def pull(self, account: str, now: datetime) -> tuple[list[dict[str, Any]], list[str]]: ...
    async def cancel(self, account: str, ids: list[str], now: datetime) -> None: ...


@dataclass
class _Alarm:
    id: str
    kind: str
    title: str
    fire_at: datetime
    created_by: str
    cancelled_at: datetime | None = None


@dataclass
class _Account:
    devices: dict[str, tuple[str, datetime]] = field(default_factory=dict)  # id -> (platform, last_seen)
    alarms: dict[str, _Alarm] = field(default_factory=dict)


class MemorySyncStore:
    """In-process store for development: every linked device must use this same API."""

    def __init__(self) -> None:
        self._accounts: dict[str, _Account] = {}

    def _get(self, account: str) -> _Account:
        return self._accounts.setdefault(account, _Account())

    async def touch_device(self, account: str, device_id: str, platform: str, now: datetime) -> None:
        self._get(account).devices[device_id] = (platform, now)

    async def other_devices(self, account: str, device_id: str, now: datetime) -> list[str]:
        devices = self._get(account).devices
        return sorted(p for d, (p, seen) in devices.items() if d != device_id and now - seen <= ACTIVE_DEVICE_WINDOW)

    async def publish(self, account: str, device_id: str, alarm: dict[str, Any]) -> None:
        alarms = self._get(account).alarms
        if alarm["id"] not in alarms:  # publishing twice (a retry) changes nothing
            alarms[alarm["id"]] = _Alarm(
                alarm["id"], alarm["kind"], alarm["title"], datetime.fromisoformat(alarm["fire_at"]), device_id
            )

    async def pull(self, account: str, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
        acc = self._get(account)
        # Past alarms are of no use to anyone: forget them.
        acc.alarms = {k: a for k, a in acc.alarms.items() if a.fire_at > now}
        upcoming = sorted(acc.alarms.values(), key=lambda a: a.fire_at)
        active = [
            {"id": a.id, "kind": a.kind, "title": a.title, "fire_at": _iso(a.fire_at)}
            for a in upcoming
            if a.cancelled_at is None
        ]
        return active, [a.id for a in upcoming if a.cancelled_at is not None]

    async def cancel(self, account: str, ids: list[str], now: datetime) -> None:
        for i in ids:
            alarm = self._get(account).alarms.get(i)
            if alarm and alarm.cancelled_at is None:
                alarm.cancelled_at = now


class SupabaseSyncStore:
    """sync_devices / sync_alarms through PostgREST with the service role key (server only;
    RLS has no policies, so the app's anon key cannot read these tables)."""

    def __init__(self, url: str, service_key: str, http: httpx.AsyncClient) -> None:
        self._rest = url.rstrip("/") + "/rest/v1"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._http = http

    async def _call(self, method: str, table: str, *, params: dict[str, str] | None = None,
                    json: Any = None, prefer: str | None = None) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        r = await self._http.request(method, f"{self._rest}/{table}", params=params, json=json, headers=headers)
        r.raise_for_status()
        return r.json() if r.content else None

    async def touch_device(self, account: str, device_id: str, platform: str, now: datetime) -> None:
        await self._call(
            "POST", "sync_devices",
            params={"on_conflict": "account_hash,device_id"},
            json={"account_hash": account, "device_id": device_id, "platform": platform, "last_seen": _iso(now)},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def other_devices(self, account: str, device_id: str, now: datetime) -> list[str]:
        rows = await self._call("GET", "sync_devices", params={
            "select": "platform",
            "account_hash": f"eq.{account}",
            "device_id": f"neq.{device_id}",
            "last_seen": f"gte.{_iso(now - ACTIVE_DEVICE_WINDOW)}",
        })
        return sorted(r["platform"] for r in rows or [])

    async def publish(self, account: str, device_id: str, alarm: dict[str, Any]) -> None:
        await self._call(
            "POST", "sync_alarms",
            params={"on_conflict": "id"},
            json={**alarm, "account_hash": account, "created_by": device_id},
            prefer="resolution=ignore-duplicates,return=minimal",
        )

    async def pull(self, account: str, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
        rows = await self._call("GET", "sync_alarms", params={
            "select": "id,kind,title,fire_at,cancelled_at",
            "account_hash": f"eq.{account}",
            "fire_at": f"gt.{_iso(now)}",
            "order": "fire_at.asc",
        })
        active = [
            {"id": r["id"], "kind": r["kind"], "title": r["title"], "fire_at": _iso(datetime.fromisoformat(r["fire_at"]))}
            for r in rows or []
            if r["cancelled_at"] is None
        ]
        return active, [r["id"] for r in rows or [] if r["cancelled_at"] is not None]

    async def cancel(self, account: str, ids: list[str], now: datetime) -> None:
        await self._call(
            "PATCH", "sync_alarms",
            params={"account_hash": f"eq.{account}", "id": f"in.({','.join(ids)})", "cancelled_at": "is.null"},
            json={"cancelled_at": _iso(now)},
            prefer="return=minimal",
        )


def make_store(supabase_url: str | None, service_key: str | None, http: httpx.AsyncClient) -> SyncStore:
    if supabase_url and service_key:
        return SupabaseSyncStore(supabase_url, service_key, http)
    return MemorySyncStore()
