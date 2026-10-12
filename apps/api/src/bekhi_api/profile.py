"""Who the user is to BEKHI (set_profile; GET/POST /api/v1/profile): their name, their city and what
the day's briefing tells them. One profile per account (the sync code, as todos.py), so the phone and
the computer know the same person.

Supabase holds it when SUPABASE_URL is set (the `profiles` table, supabase/migrations); until that
table exists, and without Supabase, a JSON file per account next to PROFILE_FILE. Profiles are
personal: never logged."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import API_ROOT
from .models import ActionResult
from .sync import supabase_headers

log = logging.getLogger(__name__)

BRIEFING_PARTS = ("weather", "todos", "schedule", "email", "news")
# Until the user chooses (the briefing asks them once).
DEFAULT_BRIEFING = ["weather", "todos", "schedule"]
PART_MN = {"weather": "цаг агаар", "todos": "хийх зүйлс", "schedule": "товлосон зүйлс", "email": "шинэ имэйл",
           "news": "мэдээ"}
MAX_NAME, MAX_CITY = 40, 60


class ProfileStore(Protocol):
    async def get(self, account: str | None) -> dict[str, Any]: ...
    async def put(self, account: str | None, profile: dict[str, Any]) -> None: ...


class FileProfileStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _path(account: str | None) -> Path:
        base = Path(os.getenv("PROFILE_FILE") or API_ROOT / "data" / "profile.json")
        return base if account is None else base.with_name(f"profile-{account}.json")

    async def get(self, account: str | None) -> dict[str, Any]:
        with self._lock:
            try:
                return json.loads(self._path(account).read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                return {}

    async def put(self, account: str | None, profile: dict[str, Any]) -> None:
        with self._lock:
            p = self._path(account)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(p)


class SupabaseProfileStore:
    """The `profiles` table through PostgREST with the service role key (server only). A database
    without the table yet (404) keeps profiles in `fallback` instead of failing."""

    def __init__(self, url: str, service_key: str, http: httpx.AsyncClient, fallback: FileProfileStore) -> None:
        self._rest = url.rstrip("/") + "/rest/v1/profiles"
        self._headers = supabase_headers(service_key)
        self._http = http
        self._fallback = fallback
        self._missing = False

    async def _call(self, method: str, **kw: Any) -> Any:
        r = await self._http.request(method, self._rest, headers={**self._headers, **kw.pop("headers", {})}, **kw)
        if r.status_code == 404:
            log.warning("supabase has no profiles table yet: keeping profiles in a file")
            self._missing = True
            return None
        r.raise_for_status()
        return r.json() if r.content else None

    async def get(self, account: str | None) -> dict[str, Any]:
        if account is None or self._missing:
            return await self._fallback.get(account)
        rows = await self._call("GET", params={"select": "data", "account_hash": f"eq.{account}"})
        if self._missing:
            return await self._fallback.get(account)
        return dict(rows[0]["data"]) if rows else {}

    async def put(self, account: str | None, profile: dict[str, Any]) -> None:
        if account is None or self._missing:
            return await self._fallback.put(account, profile)
        row = {"account_hash": account, "data": profile, "updated_at": datetime.now(UTC).isoformat()}
        await self._call("POST", json=row, headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        if self._missing:
            await self._fallback.put(account, profile)


def make_store(supabase_url: str | None, service_key: str | None, http: httpx.AsyncClient) -> ProfileStore:
    if supabase_url and service_key:
        return SupabaseProfileStore(supabase_url, service_key, http, FileProfileStore())
    return FileProfileStore()


def _parts(values: Any) -> list[str]:
    """Known parts, in BEKHI's order, each once."""
    wanted = set(values) if isinstance(values, list) else set()
    return [p for p in BRIEFING_PARTS if p in wanted]


def clean(profile: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(profile.get("name"), str) and profile["name"].strip():
        out["name"] = profile["name"].strip()[:MAX_NAME]
    if isinstance(profile.get("city"), str) and profile["city"].strip():
        out["city"] = profile["city"].strip()[:MAX_CITY]
    if "briefing" in profile and profile["briefing"] is not None:
        out["briefing"] = _parts(profile["briefing"])
    return out


def briefing_parts(profile: dict[str, Any]) -> list[str]:
    return profile["briefing"] if "briefing" in profile else list(DEFAULT_BRIEFING)


async def update(store: ProfileStore, account: str | None, changes: dict[str, Any]) -> dict[str, Any]:
    """Merges the changes: a name or city ("" drops it), the briefing's parts (exactly, or added and removed)."""
    profile = clean(await store.get(account))
    for key in ("name", "city"):
        if key in changes and changes[key] is not None:
            profile[key] = str(changes[key])
    if changes.get("briefing") is not None:
        profile["briefing"] = changes["briefing"]
    if changes.get("briefing_add") or changes.get("briefing_remove"):
        parts = set(briefing_parts(profile)) | set(changes.get("briefing_add") or [])
        profile["briefing"] = list(parts - set(changes.get("briefing_remove") or []))
    profile = clean(profile)
    await store.put(account, profile)
    return profile


def _list_mn(parts: list[str]) -> str:
    words = [PART_MN[p] for p in parts]
    return ", ".join(words[:-1]) + f" болон {words[-1]}" if len(words) > 1 else "".join(words)


async def set_profile(action_id: str, args: dict[str, Any], store: ProfileStore, account: str | None) -> ActionResult:
    profile = await update(store, account, args)
    said = []
    if args.get("name") is not None:
        said.append(f"таныг {profile['name']} гэж дуудна" if profile.get("name") else "нэрээр тань дуудахаа болилоо")
    if args.get("city"):
        said.append(f"цаг агаарыг {profile['city']} хотоор хэлнэ")  # the name as said: no case ending to get wrong
    if any(args.get(k) is not None for k in ("briefing", "briefing_add", "briefing_remove")):
        parts = briefing_parts(profile)
        said.append(f"өдрийн тоймд {_list_mn(parts)} хэлнэ" if parts else "өдрийн тойм одоо зөвхөн мэндчилгээ байна")
    summary = "За, " + ", ".join(said) + "." if said else "За, хадгаллаа."
    return ActionResult(action_id=action_id, tool="set_profile", status="succeeded", executed_via="backend",
                        error_code=None, data={"summary_mn": summary, "profile": profile})


def prompt_line(profile: dict[str, Any]) -> str:
    """What the planner is told about the user ("" when nothing is known)."""
    bits = []
    if profile.get("name"):
        bits.append(f"their name is {profile['name']}")
    if profile.get("city"):
        bits.append(f"they live in {profile['city']} (the weather's place when they name none)")
    return f"About the user: {'; '.join(bits)}." if bits else ""
