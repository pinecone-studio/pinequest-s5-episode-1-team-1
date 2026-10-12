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
    assert await google.status(ACCOUNT) == {"linked": True, "email": "bold@gmail.com", "tasks": False, "send": False}
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


class FakeTasks(FakeGoogle):
    """Google, with Tasks allowed and a Tasks list."""

    def __init__(self, enabled: bool = True):
        super().__init__()
        self.enabled = enabled
        self.tasks: dict[str, dict] = {"t0": {"id": "t0", "title": "Ном буцаах", "status": "needsAction",
                                              "due": "2026-10-09T00:00:00.000Z", "updated": "2026-10-01T00:00:00Z"}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(google_link.TOKEN_URL):
            r = super().__call__(request)
            body = r.json()
            if "scope" in body:
                body["scope"] += " " + google_link.TASKS_SCOPE
            return httpx.Response(200, json=body)
        if request.url.host != "tasks.googleapis.com":
            return super().__call__(request)
        if not self.enabled:
            return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})
        task_id = request.url.path.rsplit("/", 1)[-1]
        if request.method == "GET":
            return httpx.Response(200, json={"items": list(self.tasks.values())})
        if request.method == "POST":
            body = json.loads(request.content)
            new_id = f"t{len(self.tasks)}"
            self.tasks[new_id] = {"id": new_id, "status": "needsAction", "updated": "2026-10-12T00:00:00Z", **body}
            return httpx.Response(200, json=self.tasks[new_id])
        if request.method == "PATCH":
            self.tasks[task_id].update(json.loads(request.content))
            return httpx.Response(200, json=self.tasks[task_id])
        if request.method == "DELETE":
            self.tasks.pop(task_id)
            return httpx.Response(204)
        return httpx.Response(404)


async def test_the_to_do_list_is_the_google_tasks_list_once_linked(tmp_path, monkeypatch):
    from bekhi_api import todos
    from datetime import datetime

    monkeypatch.setenv("TODO_FILE", str(tmp_path / "todos.json"))
    fake = FakeTasks()
    google, _ = await linked(tmp_path, fake)
    store = todos.GoogleTasksTodoStore(google, todos.FileTodoStore())
    now = datetime.fromisoformat("2026-10-08T12:00:00+08:00")

    # A task made in Google's own app shows up, due by the end of its day.
    listed = await todos.list_todos("l", {"filter": "all"}, now, store, ACCOUNT)
    assert listed.data["items"] == [{"title": "Ном буцаах", "due_at": "2026-10-09T23:59:00+08:00", "done": False}]

    await todos.add_todo("a", {"title": "Тайлан илгээх", "due_at": "2026-10-09T09:00:00+08:00"}, now, store, ACCOUNT)
    added = fake.tasks["t1"]
    assert added["title"] == "Тайлан илгээх" and added["due"] == "2026-10-09T00:00:00.000Z"
    assert (await todos.complete_todo("c", {"query": "тайлан"}, store, ACCOUNT)).status == "succeeded"
    assert fake.tasks["t1"]["status"] == "completed"
    assert (await todos.delete_todo("d", {"query": "ном"}, store, ACCOUNT)).status == "succeeded"
    assert list(fake.tasks) == ["t1"]
    # Another account, without Google, keeps BEKHI's own list.
    await todos.add_todo("a", {"title": "Сүү авах"}, now, store, "b" * 64)
    assert "Сүү авах" not in [t["title"] for t in fake.tasks.values()]


async def test_tasks_not_enabled_for_the_project_falls_back_to_bekhis_list(tmp_path, monkeypatch):
    from bekhi_api import todos
    from datetime import datetime

    monkeypatch.setenv("TODO_FILE", str(tmp_path / "todos.json"))
    google, _ = await linked(tmp_path, FakeTasks(enabled=False))
    store = todos.GoogleTasksTodoStore(google, todos.FileTodoStore())
    now = datetime.fromisoformat("2026-10-08T12:00:00+08:00")
    await todos.add_todo("a", {"title": "Сүү авах"}, now, store, ACCOUNT)
    assert [i["title"] for i in (await todos.list_todos("l", {"filter": "all"}, now, store, ACCOUNT)).data["items"]] == ["Сүү авах"]


class FakeDrafts(FakeGoogle):
    """Google, with writing mail allowed: drafts are kept, and sent ones listed."""

    def __init__(self, compose: bool = True):
        super().__init__()
        self.compose = compose
        self.drafts: dict[str, dict] = {}
        self.sent: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(google_link.TOKEN_URL):
            r = super().__call__(request)
            body = r.json()
            if "scope" in body and self.compose:
                body["scope"] += " " + google_link.COMPOSE_SCOPE
            return httpx.Response(200, json=body)
        path = request.url.path
        if path.endswith("/messages/18c0a1b2c3d4e5f6") and request.url.params.get("format") == "metadata" \
                and "Message-ID" in request.url.params.get_list("metadataHeaders"):
            return httpx.Response(200, json={"id": "18c0a1b2c3d4e5f6", "threadId": "th1", "payload": {"headers": [
                {"name": "From", "value": "Бат Болд <bat@example.com>"}, {"name": "Subject", "value": "Уулзалт"},
                {"name": "Message-Id", "value": "<m1@example.com>"}]}})
        if path.endswith("/drafts") and request.method == "POST":
            body = json.loads(request.content)
            draft_id = f"r{len(self.drafts) + 1}"
            self.drafts[draft_id] = body["message"]
            return httpx.Response(200, json={"id": draft_id, "message": {"id": "x"}})
        if path.endswith("/drafts/send"):
            draft_id = json.loads(request.content)["id"]
            if draft_id not in self.drafts:
                return httpx.Response(404, json={"error": {"code": 404}})
            self.sent.append(draft_id)
            self.drafts.pop(draft_id)
            return httpx.Response(200, json={"id": "sent1"})
        if "/drafts/" in path and request.method == "DELETE":
            self.drafts.pop(path.rsplit("/", 1)[-1], None)
            return httpx.Response(204)
        return super().__call__(request)


def mime_of(message: dict) -> str:
    return base64.urlsafe_b64decode(message["raw"] + "==").decode("utf-8")


async def test_a_reply_is_a_draft_in_the_thread_and_is_sent_only_in_a_later_turn(tmp_path):
    fake = FakeDrafts()
    google, _ = await linked(tmp_path, fake)
    assert (await google.status(ACCOUNT))["send"] is True
    drafted = await google_link.run_mail_tool("d", "draft_email", {"reply_to": "18c0a1b2c3d4e5f6",
                                                                   "body": "Маргааш уулзъя."}, google, ACCOUNT, "req-1")
    assert drafted.status == "succeeded"
    assert drafted.data["summary_mn"] == "Хариуны ноорог бэлэн: «Маргааш уулзъя.». Хүлээн авагч: Бат Болд. Илгээх үү?"
    message = fake.drafts["r1"]
    assert message["threadId"] == "th1"
    mime = mime_of(message)
    assert "To: =?utf-8?" in mime or "Бат Болд" in mime  # the name may be encoded
    assert "bat@example.com" in mime and "Subject: Re: " in mime and "In-Reply-To: <m1@example.com>" in mime

    # The model may not send what the user has not seen yet.
    same = await google_link.run_mail_tool("s", "send_email", {}, google, ACCOUNT, "req-1")
    assert same.error_code == "EMAIL_NOT_CONFIRMED" and fake.sent == []
    # "Тийм" in the next turn sends it, once.
    assert (await google_link.run_mail_tool("s", "send_email", {}, google, ACCOUNT, "req-2")).status == "succeeded"
    assert fake.sent == ["r1"]
    assert (await google_link.run_mail_tool("s", "send_email", {}, google, ACCOUNT, "req-3")).error_code == "EMAIL_NO_DRAFT"


async def test_writing_mail_needs_the_permission_and_a_recipient(tmp_path):
    google, _ = await linked(tmp_path, FakeDrafts(compose=False))  # linked before BEKHI could write mail
    no = await google_link.run_mail_tool("d", "draft_email", {"reply_to": "18c0a1b2c3d4e5f6", "body": "x"}, google,
                                         ACCOUNT, "r")
    assert no.error_code == "GMAIL_NO_SEND"
    google, _ = await linked(tmp_path, FakeDrafts())
    nobody = await google_link.run_mail_tool("d", "draft_email", {"body": "x"}, google, ACCOUNT, "r")
    assert nobody.error_code == "EMAIL_NO_RECIPIENT"
    new = await google_link.run_mail_tool("d", "draft_email", {"to": "saraa@example.com", "subject": "Тайлан",
                                                               "body": "Тайланг хавсаргав."}, google, ACCOUNT, "r")
    assert new.data["summary_mn"].startswith("Имэйлийн ноорог бэлэн: «Тайланг хавсаргав.».")


def test_the_draft_card_sends_or_throws_away(client, tmp_path):
    fake = FakeDrafts()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    google = google_link.Google("cid", "csecret", KEY, google_link.FileLinkStore(tmp_path), http)
    client.app.state.google = google
    code = {"X-Bekhi-Sync": "ABCDEFGHJKMN", "X-Bekhi-Device": "web-1234567890abcdef"}
    from bekhi_api import sync

    account = sync.account_key("ABCDEFGHJKMN")
    record = {"email": "bold@gmail.com", "scopes": google_link.COMPOSE_SCOPE,
              "refresh_token": Fernet(KEY.encode()).encrypt(b"rt").decode()}
    (tmp_path / f"google-{account}.json").write_text(json.dumps(record), encoding="utf-8")
    fake.drafts["r9"] = {"raw": ""}
    fake.drafts["r8"] = {"raw": ""}
    assert client.post("/api/v1/google/drafts/r9/send", headers=code).json() == {"ok": True}
    assert fake.sent == ["r9"]
    assert client.post("/api/v1/google/drafts/r8/delete", headers=code).json() == {"ok": True}
    assert "r8" not in fake.drafts
    assert client.post("/api/v1/google/drafts/r9/send", headers=code).status_code == 404  # already sent
    assert client.post("/api/v1/google/drafts/r7/forward", headers=code).status_code == 422
