"""Agent loop, web search and opening apps/sites."""

from __future__ import annotations

from types import SimpleNamespace

from google.genai import errors, types

from bekhi_api import desktop
from bekhi_api import main as main_mod
from bekhi_api.pipeline import MAX_AGENT_STEPS
from bekhi_api.providers.base import SearchError

from .conftest import context


def chat(client, text):
    r = client.post("/api/v1/assistant/chat", json={"text": text, "context": context()})
    assert r.status_code == 200, r.text
    return r.json()


class FakeSearch:
    def __init__(self, error: Exception | None = None) -> None:
        self.queries: list[str] = []
        self.error = error

    async def search(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return {"answer": "Pinecone Academy бол програмчлалын сургууль.", "sources": [{"title": "pinecone.mn", "url": "https://pinecone.mn"}]}


def test_search_then_answer(client, planner, monkeypatch):
    search = FakeSearch()
    monkeypatch.setattr(main_mod, "get_search", lambda http: search)
    planner.then(("web_search", {"user_request": "Pinecone Academy гэж юу вэ", "query": "Pinecone Academy"}))
    planner.after_tools(("reply", {"user_request": "Pinecone Academy гэж юу вэ", "text": "Pinecone Academy бол програмчлалын сургууль юм."}))

    turn = chat(client, "Pinecone Academy-ийн талаар хайгаад хэлээч")
    assert search.queries == ["Pinecone Academy"]
    [(call, result)] = planner.followups[0]
    assert call.name == "web_search" and "програмчлалын сургууль" in result["answer"]
    assert turn["stage"] == "final"
    assert turn["response"] == "Pinecone Academy бол програмчлалын сургууль юм."  # the model's words, not repeated


def test_search_without_quota_is_explained(client, planner, monkeypatch):
    monkeypatch.setattr(main_mod, "get_search", lambda http: FakeSearch(SearchError("WEB_SEARCH_LIMIT")))
    planner.then(("web_search", {"user_request": "MacBook үнэ", "query": "MacBook үнэ"}))

    turn = chat(client, "Хамгийн хямд MacBook хайгаад хэл")
    told = planner.followups[0][0][1]
    assert told["error"] == "WEB_SEARCH_LIMIT" and "1000" in told["reason"]  # the model knows why
    assert "1000" in turn["response"]  # the model said nothing more, so the fixed sentence explains


def test_agent_loop_is_bounded(client, planner, monkeypatch):
    monkeypatch.setattr(main_mod, "get_search", lambda http: FakeSearch())
    again = ("web_search", {"user_request": "x", "query": "дахин"})
    planner.then(again)
    for _ in range(MAX_AGENT_STEPS + 3):
        planner.after_tools(again)

    chat(client, "Хайгаад бай")
    assert len(planner.followups) == MAX_AGENT_STEPS


def test_search_then_open_the_site(client, planner, monkeypatch):
    monkeypatch.setattr(main_mod, "get_search", lambda http: FakeSearch())
    planner.then(("web_search", {"user_request": "Pinecone сайт нээх", "query": "Pinecone Academy website"}))
    planner.after_tools(("open_url", {"user_request": "Pinecone сайт нээх", "url": "https://pinecone.mn", "title": "Pinecone Academy"}))

    turn = chat(client, "Pinecone Academy-ийн сайтыг олоод нээгээрэй")
    assert turn["stage"] == "awaiting_device"
    assert [a["tool"] for a in turn["actions"]] == ["web_search", "open_url"]


def test_only_web_links_are_opened(client, planner):
    planner.then(("open_url", {"user_request": "x", "url": "file:///C:/Windows/System32/cmd.exe"}))
    assert chat(client, "Энийг нээ")["intent"] == "error"


def test_find_app_uses_the_start_menu(tmp_path):
    programs = tmp_path / "Programs"
    (programs / "Visual Studio Code").mkdir(parents=True)
    (programs / "Visual Studio Code" / "Visual Studio Code.lnk").write_bytes(b"")
    (programs / "Visual Studio Code" / "Uninstall Visual Studio Code.lnk").write_bytes(b"")
    (programs / "Google Chrome.lnk").write_bytes(b"")

    assert desktop.find_app("VS Code", [programs]).endswith("Visual Studio Code.lnk")
    assert desktop.find_app("Хром", [programs]).endswith("Google Chrome.lnk")
    assert desktop.find_app("Calculator", [programs]) == "calc.exe"
    assert desktop.find_app("Photoshop", [programs]) is None


def test_open_app_on_the_pc(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(desktop, "find_app", lambda name: "C:/x/Spotify.lnk" if name == "Spotify" else None)
    monkeypatch.setattr(desktop.os, "startfile", opened.append, raising=False)
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    assert desktop.run("open_app", {"app_name": "Spotify"}, s)["status"] == "succeeded"
    assert desktop.run("open_app", {"app_name": "Photoshop"}, s)["error_code"] == "APP_NOT_FOUND"
    assert opened == ["C:/x/Spotify.lnk"]


def test_open_outcomes(client, planner):
    def report(tool, args, status, via, code=None):
        planner.then((tool, {"user_request": "x", **args}))
        turn = chat(client, "нээ")
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [{"action_id": "a1", "tool": tool, "status": status, "executed_via": via, "error_code": code}],
        })
        return r.json()["response"]

    assert report("open_app", {"app_name": "VS Code"}, "succeeded", "backend") == "За, VS Code нээлээ."
    assert "'Photoshop'" in report("open_app", {"app_name": "Photoshop"}, "failed", "backend", "APP_NOT_FOUND")
    assert "iOS" in report("open_app", {"app_name": "VS Code"}, "unsupported", None, "IOS_CANNOT_OPEN_APPS")
    assert "Android" in report("open_app", {"app_name": "VS Code"}, "unsupported", None, "ANDROID_CANNOT_OPEN_APPS")
    assert report("open_url", {"url": "https://youtube.com", "title": "YouTube"}, "handed_off", "url_scheme") == "За, YouTube нээлээ."


async def test_gemini_follow_up_returns_the_model_turn_unchanged():
    from bekhi_api.providers.base import FunctionCall
    from bekhi_api.providers.gemini import GeminiPlanner

    sent = []
    model_turn = types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="web_search", args={"query": "x"}), thought_signature=b"sig")])

    class Models:
        async def generate_content(self, model, contents, config):
            sent.append(list(contents))
            calls = [SimpleNamespace(name="web_search", args={"query": "x"})] if len(sent) == 1 else [SimpleNamespace(name="reply", args={"text": "ok"})]
            return SimpleNamespace(candidates=[SimpleNamespace(content=model_turn)], function_calls=calls)

    client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    planner = GeminiPlanner(client, ["gemini-3.5-flash-lite"])
    first = await planner.plan(system="s", history=[], user_text="хайгаад хэл", functions=[])
    second = await planner.follow_up([(first[0], {"answer": "y"})])
    assert second[0].name == "reply"
    assert sent[1][-2] is model_turn  # with its thought signature
    assert sent[1][-1].parts[0].function_response.name == "web_search"
    assert sent[1][-1].parts[0].function_response.response == {"answer": "y"}
    assert isinstance(first[0], FunctionCall)


def test_what_could_not_be_done_is_said_after_the_outcome(client, planner):
    planner.then(
        ("open_app", {"user_request": "VS Code нээгээд project ажиллуулах", "app_name": "VS Code"}),
        ("explain_limitation", {"user_request": "x", "code": "other", "message": "Project-оо өөрөө ажиллуулж чадахгүй.",
                                "alternative_kind": "none", "alternative_description": ""}),
    )
    turn = chat(client, "VS Code-оо нээгээд project-оо ажиллуул")
    assert turn["stage"] == "awaiting_device"
    r = client.post("/api/v1/assistant/actions/results", json={
        "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
        "results": [{"action_id": "a1", "tool": "open_app", "status": "succeeded", "executed_via": "backend", "error_code": None}],
    })
    assert r.json()["response"] == "За, VS Code нээлээ. Project-оо өөрөө ажиллуулж чадахгүй."


async def test_tavily_request_and_errors():
    import json

    import httpx

    from bekhi_api.providers.tavily import TavilyWebSearch

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        if seen.get("status"):
            return httpx.Response(seen["status"], json={"detail": {"error": "x"}})
        return httpx.Response(200, json={"answer": "Pinecone Academy is a coding school.", "results": [
            {"title": "Pinecone", "url": "https://pinecone.mn", "content": "a" * 2000, "score": 0.9}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        search = TavilyWebSearch(http, "tvly-test")
        found = await search.search("Pinecone Academy")
        assert seen["auth"] == "Bearer tvly-test"
        assert seen["body"]["query"] == "Pinecone Academy" and seen["body"]["search_depth"] == "basic"
        assert seen["body"]["country"] == "mongolia"
        assert found["answer"].startswith("Pinecone") and len(found["results"][0]["content"]) == 600
        assert found["sources"] == [{"title": "Pinecone", "url": "https://pinecone.mn"}]

        for status, code in [(401, "WEB_SEARCH_KEY_INVALID"), (432, "WEB_SEARCH_LIMIT"), (500, "WEB_SEARCH_FAILED")]:
            seen["status"] = status
            try:
                await search.search("x")
                raise AssertionError("expected SearchError")
            except SearchError as e:
                assert e.code == code


async def test_gemini_search_without_quota():
    from bekhi_api.providers.gemini import GeminiWebSearch

    class Models:
        async def generate_content(self, model, contents, config):
            raise errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    search = GeminiWebSearch(SimpleNamespace(aio=SimpleNamespace(models=Models())), "gemini-3.5-flash-lite")
    try:
        await search.search("x")
        raise AssertionError("expected SearchError")
    except SearchError as e:
        assert e.code == "WEB_SEARCH_UNAVAILABLE"


def test_search_provider_needs_a_key(monkeypatch):
    import httpx

    from bekhi_api import providers
    from bekhi_api.config import get_settings
    from bekhi_api.providers.tavily import TavilyWebSearch

    s = get_settings()
    monkeypatch.setattr(providers, "get_settings", lambda: s.__class__(**{**s.__dict__, "web_search_provider": "tavily", "tavily_api_key": None}))
    assert providers.get_search(httpx.AsyncClient()) is None
    monkeypatch.setattr(providers, "get_settings", lambda: s.__class__(**{**s.__dict__, "web_search_provider": "tavily", "tavily_api_key": "tvly-x"}))
    assert isinstance(providers.get_search(httpx.AsyncClient()), TavilyWebSearch)
