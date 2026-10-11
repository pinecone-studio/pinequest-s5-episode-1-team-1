"""Gmail for BEKHI: the user links their Google account once (OAuth, read-only Gmail), then the
agent can check and read their mail (check_email, read_email) and tell it in Mongolian.

The link belongs to the sync account, so every device linked with the same code can use it. The
refresh token is encrypted (GOOGLE_TOKEN_KEY). On the user's own computer (desktop.py) it is
kept in a file there; elsewhere in Supabase when configured. Mail is read only when asked and
never stored or logged: only who sent it, the subject, a snippet, or the text of one message.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .models import ActionResult
from .sync import supabase_headers

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "openid email profile https://www.googleapis.com/auth/gmail.readonly"
STATE_TTL = 600  # seconds the user has to finish signing in
MAX_TEXT = 6_000


class LinkStore(Protocol):
    async def get(self, account: str) -> dict[str, Any] | None: ...
    async def put(self, account: str, record: dict[str, Any]) -> None: ...
    async def delete(self, account: str) -> None: ...


class FileLinkStore:
    """On the user's computer: the link stays there, in their profile."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def _path(self, account: str) -> Path:
        return self._folder / f"google-{account}.json"

    async def get(self, account: str) -> dict[str, Any] | None:
        try:
            return json.loads(self._path(account).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    async def put(self, account: str, record: dict[str, Any]) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        self._path(account).write_text(json.dumps(record), encoding="utf-8")

    async def delete(self, account: str) -> None:
        self._path(account).unlink(missing_ok=True)


class SupabaseLinkStore:
    """The google_links table, server only (RLS with no policies), as todos and memories."""

    def __init__(self, url: str, service_key: str, http: httpx.AsyncClient) -> None:
        self._rest = url.rstrip("/") + "/rest/v1/google_links"
        self._headers = supabase_headers(service_key)
        self._http = http

    async def get(self, account: str) -> dict[str, Any] | None:
        r = await self._http.get(self._rest, params={"select": "*", "account_hash": f"eq.{account}"}, headers=self._headers)
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    async def put(self, account: str, record: dict[str, Any]) -> None:
        r = await self._http.post(self._rest, params={"on_conflict": "account_hash"}, json={**record, "account_hash": account},
                                  headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"})
        r.raise_for_status()

    async def delete(self, account: str) -> None:
        r = await self._http.delete(self._rest, params={"account_hash": f"eq.{account}"}, headers=self._headers)
        r.raise_for_status()


@dataclass
class _Pending:
    account: str
    redirect_uri: str
    expires: float


class Google:
    """The OAuth client, the links, and Gmail."""

    def __init__(self, client_id: str, client_secret: str, token_key: str, store: LinkStore,
                 http: httpx.AsyncClient) -> None:
        self._client_id, self._client_secret = client_id, client_secret
        self._fernet = Fernet(token_key.encode())
        self._store = store
        self._http = http
        self._pending: dict[str, _Pending] = {}
        self._access: dict[str, tuple[str, float]] = {}  # account -> (access token, expiry), memory only

    # Signing in -------------------------------------------------------------------------------------
    def start(self, account: str, redirect_uri: str) -> str:
        now = time.time()
        self._pending = {s: p for s, p in self._pending.items() if p.expires > now}
        state = secrets.token_urlsafe(24)
        self._pending[state] = _Pending(account, redirect_uri, now + STATE_TTL)
        return AUTH_URL + "?" + urlencode({
            "client_id": self._client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPES,
            "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state,
        })

    async def finish(self, state: str, code: str) -> str:
        """Stores the link for the state's account; returns the Google account's email."""
        pending = self._pending.pop(state, None)
        if pending is None or pending.expires < time.time():
            raise PermissionError("sign-in expired")
        r = await self._http.post(TOKEN_URL, data={
            "code": code, "client_id": self._client_id, "client_secret": self._client_secret,
            "redirect_uri": pending.redirect_uri, "grant_type": "authorization_code",
        })
        r.raise_for_status()
        tokens = r.json()
        if "gmail.readonly" not in tokens.get("scope", ""):
            raise PermissionError("Gmail was not allowed")
        info = (await self._http.get(USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"})).json()
        refresh = tokens.get("refresh_token")
        if not refresh:
            raise PermissionError("no refresh token")
        await self._store.put(pending.account, {
            "email": info.get("email", ""), "name": info.get("name", ""),
            "refresh_token": self._fernet.encrypt(refresh.encode()).decode(),
        })
        self._access[pending.account] = (tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600)) - 60)
        return str(info.get("email", ""))

    async def status(self, account: str) -> dict[str, Any]:
        link = await self._store.get(account)
        return {"linked": bool(link), "email": link.get("email") if link else None}

    async def unlink(self, account: str) -> None:
        link = await self._store.get(account)
        if link:
            try:
                await self._http.post(REVOKE_URL, data={"token": self._fernet.decrypt(link["refresh_token"].encode()).decode()})
            except (httpx.HTTPError, InvalidToken):
                pass  # forgotten here either way
            await self._store.delete(account)
        self._access.pop(account, None)

    # Gmail ------------------------------------------------------------------------------------------
    async def _token(self, account: str) -> str | None:
        cached = self._access.get(account)
        if cached and cached[1] > time.time():
            return cached[0]
        link = await self._store.get(account)
        if not link:
            return None
        try:
            refresh = self._fernet.decrypt(link["refresh_token"].encode()).decode()
        except InvalidToken:
            return None
        r = await self._http.post(TOKEN_URL, data={
            "refresh_token": refresh, "client_id": self._client_id, "client_secret": self._client_secret,
            "grant_type": "refresh_token",
        })
        if r.status_code in (400, 401):  # revoked, or a Testing app's week has passed
            raise PermissionError("relink")
        r.raise_for_status()
        tokens = r.json()
        self._access[account] = (tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600)) - 60)
        return tokens["access_token"]

    async def _gmail(self, account: str, path: str, **params: Any) -> Any:
        token = await self._token(account)
        if token is None:
            raise LookupError("not linked")
        r = await self._http.get(GMAIL + path, params=params, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 401:
            self._access.pop(account, None)
            raise PermissionError("relink")
        r.raise_for_status()
        return r.json()

    async def check_email(self, account: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        listing = await self._gmail(account, "/messages", q=args.get("query") or "in:inbox",
                                    maxResults=int(args.get("limit") or 5))
        emails = []
        for m in listing.get("messages", []):
            msg = await self._gmail(account, f"/messages/{m['id']}", format="metadata",
                                    metadataHeaders=["From", "Subject", "Date"])
            head = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"], "from": _sender(head.get("From", "")), "subject": head.get("Subject", ""),
                "date": head.get("Date", ""), "snippet": msg.get("snippet", ""),
                "unread": "UNREAD" in msg.get("labelIds", []),
            })
        return emails

    async def read_email(self, account: str, message_id: str) -> dict[str, Any]:
        msg = await self._gmail(account, f"/messages/{message_id}", format="full")
        head = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        text = _body_text(msg.get("payload", {}))
        return {"from": _sender(head.get("From", "")), "subject": head.get("Subject", ""), "date": head.get("Date", ""),
                "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}


def _sender(value: str) -> str:
    """"Бат Болд <bat@example.com>" -> "Бат Болд": a name to say, not an address to read out."""
    name = re.sub(r"\s*<[^>]+>\s*$", "", value).strip().strip('"')
    return name or value


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _body_text(payload: dict[str, Any]) -> str:
    """The message's plain text, or its HTML as text."""
    plain, markup = [], []
    stack = [payload]
    while stack:
        part = stack.pop()
        stack.extend(part.get("parts", []) or [])
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        if part.get("mimeType") == "text/plain":
            plain.append(_decode(data))
        elif part.get("mimeType") == "text/html":
            markup.append(_decode(data))
    if plain:
        return "\n".join(plain).strip()
    if markup:
        from .webpage import page_text

        return page_text("\n".join(markup))[1]
    return ""


def make(settings: Any, http: httpx.AsyncClient, on_pc: bool, data_dir: Path) -> Google | None:
    if not (settings.google_client_id and settings.google_client_secret and settings.google_token_key):
        return None
    if on_pc or not (settings.supabase_url and settings.supabase_service_role_key):
        store: LinkStore = FileLinkStore(data_dir)
    else:
        store = SupabaseLinkStore(settings.supabase_url, settings.supabase_service_role_key, http)
    return Google(settings.google_client_id, settings.google_client_secret, settings.google_token_key, store, http)


def _fail(action_id: str, tool: str, code: str) -> ActionResult:
    return ActionResult(action_id=action_id, tool=tool, status="failed", executed_via="backend", error_code=code, data=None)


async def run_tool(action_id: str, tool: str, args: dict[str, Any], google: Google | None, account: str | None) -> ActionResult:
    if google is None:
        return _fail(action_id, tool, "GOOGLE_NOT_CONFIGURED")
    if account is None:
        return _fail(action_id, tool, "GOOGLE_NOT_LINKED")
    try:
        if tool == "check_email":
            emails = await google.check_email(account, args)
            summary = f"{len(emails)} имэйл олдлоо." if emails else "Тийм имэйл алга."
            data: dict[str, Any] = {"emails": emails, "summary_mn": summary}
        else:
            data = {**await google.read_email(account, args["id"]), "summary_mn": "Имэйлийг уншлаа."}
    except LookupError:
        return _fail(action_id, tool, "GOOGLE_NOT_LINKED")
    except PermissionError:
        return _fail(action_id, tool, "GOOGLE_RELINK")
    except httpx.HTTPError as e:
        log.warning("gmail failed: %s", type(e).__name__)
        return _fail(action_id, tool, "GMAIL_UNAVAILABLE")
    return ActionResult(action_id=action_id, tool=tool, status="succeeded", executed_via="backend", error_code=None, data=data)


def local_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BEKHI"
