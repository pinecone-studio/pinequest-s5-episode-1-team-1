"""play_video: the backend finds the first YouTube video; the device plays it."""

from __future__ import annotations

import httpx

from bekhi_api import desktop, media

from .conftest import context

RESULTS = (
    '<script>var ytInitialData = {"contents":[{"reelItemRenderer":{"videoId":"shortsAAAAA"}},'
    '{"videoRenderer":{"videoId":"qlsePDofCwM","thumbnail":{},"title":{"runs":[{"text":"Hurd - Busgui \\u0026 Live"}]}}},'
    '{"videoRenderer":{"videoId":"secondBBBBB","title":{"runs":[{"text":"Second"}]}}}]};</script>'
)


def test_the_first_ordinary_video_is_found():
    assert media.first_video(RESULTS) == ("https://www.youtube.com/watch?v=qlsePDofCwM", "Hurd - Busgui & Live")
    assert media.first_video("<html>nothing</html>") is None


def youtube(request: httpx.Request) -> httpx.Response:
    if request.url.host == "www.youtube.com":
        return httpx.Response(200, text=RESULTS)
    return httpx.Response(404)


def test_the_phone_gets_the_video_to_open_and_the_reply_names_it(client, planner):
    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(youtube))
    planner.then(("play_video", {"user_request": "x", "query": "Хүрдийн Бусгүй", "url": "https://evil.example", "title": "x"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "Хүрдийн Бусгүйг тоглуул", "context": context()}).json()
    args = turn["actions"][0]["arguments"]
    # url and title are the backend's, never the model's.
    assert args == {"query": "Хүрдийн Бусгүй", "url": "https://www.youtube.com/watch?v=qlsePDofCwM", "title": "Hurd - Busgui & Live"}

    def said(data):
        r = client.post("/api/v1/assistant/actions/results", json={
            "conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"],
            "results": [{"action_id": "a1", "tool": "play_video", "status": "handed_off", "executed_via": "url_scheme",
                         "error_code": None, "data": data}],
        })
        return r.json()["response"]

    assert said(None) == "За, YouTube дээр 'Hurd - Busgui & Live' тоглуулж байна."


def test_without_youtube_the_search_page_opens(client, planner):
    client.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    planner.then(("play_video", {"user_request": "x", "query": "Монгол дуу"}))
    turn = client.post("/api/v1/assistant/chat", json={"text": "x", "context": context()}).json()
    assert turn["actions"][0]["arguments"]["url"] == "https://www.youtube.com/results?search_query=%D0%9C%D0%BE%D0%BD%D0%B3%D0%BE%D0%BB+%D0%B4%D1%83%D1%83"


def test_the_pc_plays_one_video_at_a_time(tmp_path, monkeypatch):
    started = []

    class Window:
        def __init__(self, args):
            self.args, self.closed = args, False
            started.append(self)

        def poll(self):
            return 0 if self.closed else None

        def terminate(self):
            self.closed = True

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(desktop.subprocess, "Popen", Window)
    monkeypatch.setattr(desktop, "_player", None)
    monkeypatch.setattr(desktop, "EDGE_PATHS", [tmp_path / "msedge.exe"])
    (tmp_path / "msedge.exe").write_bytes(b"")
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    for v in ("aaaaaaaaaaa", "bbbbbbbbbbb"):
        assert desktop.run("play_video", {"query": "x", "url": f"https://www.youtube.com/watch?v={v}"}, s)["status"] == "succeeded"
    assert [w.closed for w in started] == [True, False]
    assert "--autoplay-policy=no-user-gesture-required" in started[1].args
    assert "--app=https://www.youtube.com/watch?v=bbbbbbbbbbb" in started[1].args


def test_media_keys_on_the_pc(tmp_path, monkeypatch):
    from bekhi_api import windows_controls

    pressed = []
    monkeypatch.setattr(windows_controls, "press_media_key", lambda action: pressed.append(action) or True)
    s = desktop.DesktopScheduler(tmp_path / "r.json")
    for action in ("media_play_pause", "media_next"):
        assert desktop.run("computer_control", {"action": action}, s)["status"] == "succeeded"
    assert pressed == ["media_play_pause", "media_next"]
