"""Gmail: link once with Google sign-in, then check and read mail. Google's servers are faked."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet

from bekhi_api import google_link
from bekhi_api import main as main_mod

ACCOUNT = "a" * 64
KEY = Fernet.generate_key().decode()


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class FakeGoogle:
    def __init__(self):
        self.refresh_ok = True
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.host}{request.url.path}")
        url = str(request.url)
        if url.startswith(google_link.TOKEN_URL):
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(200, json={"access_token": "at1", "refresh_token": "rt-secret", "expires_in": 3600,
                                                 "scope": "openid email https://www.googleapis.com/auth/gmail.readonly"})
            if not self.refresh_ok:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "at2", "expires_in": 3600})
        if url.startswith(google_link.USERINFO_URL):
            return httpx.Response(200, json={"email": "bold@gmail.com", "name": "Болд"})
        if request.url.path.endswith("/messages"):
            assert request.url.params["q"] == "is:unread"
            return httpx.Response(200, json={"messages": [{"id": "18c0a1b2c3d4e5f6"}]})
        if request.url.path.endswith("/messages/18c0a1b2c3d4e5f6"):
            if request.url.params["format"] == "metadata":
                return httpx.Response(200, json={"id": "18c0a1b2c3d4e5f6", "snippet": "Маргааш 10 цагт уулзъя", "labelIds": ["UNREAD"],
                                                 "payload": {"headers": [{"name": "From", "value": "Бат Болд <bat@example.com>"},
                                                                         {"name": "Subject", "value": "Уулзалт"}]}})
            return httpx.Response(200, json={"id": "18c0a1b2c3d4e5f6", "payload": {
                "headers": [{"name": "Subject", "value": "Уулзалт"}],
                "parts": [{"mimeType": "text/plain", "body": {"data": b64("Сайн уу! Маргааш 10 цагт оффис дээр уулзъя.")}}]}})
        return httpx.Response(404)


async def linked(tmp_path, fake):
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    google = google_link.Google("cid", "csecret", KEY, google_link.FileLinkStore(tmp_path), http)
    url = google.start(ACCOUNT, "http://127.0.0.1:8000/api/v1/auth/google/callback")
    state = parse_qs(urlparse(url).query)["state"][0]
    assert await google.finish(state, "auth-code") == "bold@gmail.com"
    return google, url


async def test_linking_keeps_only_an_encrypted_refresh_token(tmp_path):
    google, url = await linked(tmp_path, FakeGoogle())
    q = parse_qs(urlparse(url).query)
    assert "gmail.readonly" in q["scope"][0] and q["access_type"] == ["offline"] and q["client_id"] == ["cid"]
    saved = (tmp_path / f"google-{ACCOUNT}.json").read_text(encoding="utf-8")
    assert "rt-secret" not in saved and json.loads(saved)["email"] == "bold@gmail.com"
    assert await google.status(ACCOUNT) == {"linked": True, "email": "bold@gmail.com"}
    # A state is good once.
    try:
        await google.finish(parse_qs(urlparse(url).query)["state"][0], "again")
        raise AssertionError("state reused")
    except PermissionError:
        pass


async def test_mail_is_listed_by_name_and_read(tmp_path):
    google, _ = await linked(tmp_path, FakeGoogle())
    emails = await google.check_email(ACCOUNT, {"query": "is:unread", "limit": 5})
    assert emails == [{"id": "18c0a1b2c3d4e5f6", "from": "Бат Болд", "subject": "Уулзалт", "date": "",
                       "snippet": "Маргааш 10 цагт уулзъя", "unread": True}]
    one = await google.read_email(ACCOUNT, "18c0a1b2c3d4e5f6")
    assert one["text"] == "Сайн уу! Маргааш 10 цагт оффис дээр уулзъя."


async def test_tool_outcomes(tmp_path):
    fake = FakeGoogle()
    google, _ = await linked(tmp_path, fake)
    ok = await google_link.run_tool("e", "check_email", {"query": "is:unread"}, google, ACCOUNT)
    assert ok.status == "succeeded" and ok.data["emails"][0]["from"] == "Бат Болд"
    assert (await google_link.run_tool("e", "check_email", {}, google, "b" * 64)).error_code == "GOOGLE_NOT_LINKED"
    assert (await google_link.run_tool("e", "check_email", {}, None, ACCOUNT)).error_code == "GOOGLE_NOT_CONFIGURED"
    # A week later (Testing apps) Google refuses the refresh token: the user is asked to link again.
    google._access.clear()
    fake.refresh_ok = False
    assert (await google_link.run_tool("e", "check_email", {"query": "is:unread"}, google, ACCOUNT)).error_code == "GOOGLE_RELINK"


def test_the_callback_address_is_the_one_registered_with_google():
    def at(host, port=8000):
        return main_mod._google_redirect(SimpleNamespace(url=SimpleNamespace(hostname=host, port=port)))

    assert at("127.0.0.1") == "http://127.0.0.1:8000/api/v1/auth/google/callback"
    assert at("localhost") == "http://127.0.0.1:8000/api/v1/auth/google/callback"
    assert at("bekhi-api.onrender.com", None) == "https://bekhi-api.onrender.com/api/v1/auth/google/callback"
    assert at("192.168.1.20") is None  # a phone on the PC's Wi-Fi: Google refuses private addresses
