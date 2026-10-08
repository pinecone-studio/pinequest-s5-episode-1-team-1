from __future__ import annotations

import io
import math
import struct
import wave

from bekhi_api import main as main_mod
from bekhi_api.contracts import validate_wire
from bekhi_api.planner import DEVICE_LINES
from bekhi_api.providers import ProviderNotConfigured

from .conftest import FakeSTT, context

TZ = "Asia/Ulaanbaatar"


def chat(client, text, conversation_id=None):
    r = client.post("/api/v1/assistant/chat", json={"text": text, "context": context(conversation_id)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert validate_wire("AssistantTurn", body) == []
    return body


def report(client, turn, results):
    r = client.post(
        "/api/v1/assistant/actions/results",
        json={"conversation_id": turn["conversation_id"], "turn_id": turn["turn_id"], "results": results},
    )
    assert r.status_code == 200, r.text
    assert validate_wire("ActionResultsResponse", r.json()) == []
    return r.json()["response"]


def result(action_id, tool, status, via="native_swift", code=None):
    return {"action_id": action_id, "tool": tool, "status": status, "executed_via": via, "error_code": code}


# --- Milestone 1 -------------------------------------------------------------

def test_reminder_milestone_never_claims_before_device(client, planner):
    planner.then(("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ}))
    turn = chat(client, "Маргааш 9 цагт ажилтайг минь сануулаарай.")

    assert turn["stage"] == "awaiting_device"
    assert turn["response"] == ""
    assert turn["intent"] == "create_reminder"
    assert turn["actions"][0]["arguments"]["due_at"] == "2026-10-07T09:00:00+08:00"
    assert turn["actions"][0]["confirmation"] == {"required": False, "prompt": None}

    final = report(client, turn, [result("a1", "create_reminder", "succeeded")])
    assert final == "За, маргааш өглөө 9 цагт сануулъя."


def test_reminder_failure_is_reported_honestly(client, planner):
    planner.then(("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ}))
    turn = chat(client, "Маргааш 9 цагт ажилтайг минь сануулаарай.")
    assert report(client, turn, [result("a1", "create_reminder", "permission_denied")]) == (
        "Энэ үйлдлийг хийхийн тулд утасныхаа тохиргооноос зөвшөөрөл өгөх хэрэгтэй байна."
    )


def test_reply_text_is_dropped_while_device_action_pending(client, planner):
    planner.then(
        ("reply", {"text": "За, сануулчихлаа!"}),
        ("create_reminder", {"title": "Ажил", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ}),
    )
    turn = chat(client, "9-д сануулаарай")
    assert turn["stage"] == "awaiting_device"
    assert turn["response"] == ""


# --- Confirmation ------------------------------------------------------------

def test_call_requires_confirmation(client, planner):
    planner.then(("call_contact", {"contact_name": "Ээж", "confirmation_question": "Ээж рүү тань залгах уу?"}))
    turn = chat(client, "Ээж рүүгээ залга.")
    assert turn["stage"] == "awaiting_confirmation"
    assert turn["response"] == "Ээж рүү тань залгах уу?"
    action = turn["actions"][0]
    assert action["confirmation"] == {"required": True, "prompt": "Ээж рүү тань залгах уу?"}
    assert action["arguments"] == {"contact_name": "Ээж"}  # control field stripped

    assert report(client, turn, [result("a1", "call_contact", "handed_off", "url_scheme")]) == "За, Ээж рүү тань залгаж байна."


def test_call_passes_the_latin_spellings_to_the_phone(client, planner):
    planner.then(("call_contact", {
        "contact_name": "Майкл", "name_spellings": ["Michael", "Maikl"], "confirmation_question": "Майкл руу залгах уу?",
    }))
    turn = chat(client, "Майкл руу залга.")
    assert turn["actions"][0]["arguments"] == {"contact_name": "Майкл", "name_spellings": ["Michael", "Maikl"]}


def test_message_without_question_still_confirms(client, planner):
    planner.then(("send_message", {"contact_name": "Бат", "body": "Орой уулзъя"}))
    turn = chat(client, "Батад орой уулзъя гэж бич.")
    assert turn["requires_confirmation"] is True
    assert turn["actions"][0]["confirmation"]["prompt"]


def test_declined_confirmation(client, planner):
    planner.then(("send_message", {"contact_name": "Бат", "body": "Орой уулзъя", "confirmation_question": "Явуулах уу?"}))
    turn = chat(client, "Батад орой уулзъя гэж бич.")
    assert report(client, turn, [result("a1", "send_message", "cancelled", None)]) == "За, болиулчихлаа."


# --- Validation & limitations ---------------------------------------------------

def test_relative_dates_never_reach_the_phone(client, planner):
    planner.then(("create_reminder", {"title": "Ажил", "due_at": "tomorrow 09:00", "timezone": TZ}))
    turn = chat(client, "маргааш 9-д сануул")
    assert turn["actions"] == []
    assert turn["stage"] == "final"
    assert turn["response"] == "Уучлаарай, одоогоор ойлгоход асуудал гарлаа."


def test_the_prompt_names_the_device(client, planner):
    for platform in ("ios", "android", "web"):
        planner.then(("reply", {"text": "Сайн байна уу!"}))
        r = client.post("/api/v1/assistant/chat", json={"text": "Сайн уу", "context": context(platform=platform)})
        assert r.status_code == 200
        assert DEVICE_LINES[platform] in planner.systems[-1]


def test_wifi_is_a_limitation_not_an_action(client, planner):
    planner.then(("explain_limitation", {
        "code": "system_settings_toggle",
        "message": "Уучлаарай, iPhone апп-д Wi-Fi-г асаахыг зөвшөөрдөггүй.",
        "alternative_kind": "shortcut",
        "alternative_description": "Shortcuts дээр 'Set Wi-Fi' ашиглаж болно.",
    }))
    turn = chat(client, "Wi-Fi асаа.")
    assert turn["actions"] == []
    assert turn["intent"] == "unsupported"
    assert turn["stage"] == "final"
    assert turn["limitations"][0]["code"] == "system_settings_toggle"
    assert "Wi-Fi" in turn["response"] and "Shortcuts" in turn["response"]


def test_clarification(client, planner):
    planner.then(("ask_clarification", {"question": "Хэдэн цагт сануулах вэ?"}))
    turn = chat(client, "ажлаа сануулаарай")
    assert turn["stage"] == "awaiting_clarification"
    assert turn["requires_clarification"] is True
    assert turn["response"] == "Хэдэн цагт сануулах вэ?"


# --- Backend tools & multi-action ------------------------------------------------

def test_weather_runs_on_backend(client, planner):
    planner.then(("get_weather", {"location_name": "Улаанбаатар", "date": "2026-10-06"}))
    turn = chat(client, "Өнөөдөр Улаанбаатарт бороо орох уу?")
    assert turn["stage"] == "final"
    assert turn["actions"][0]["result"]["status"] == "succeeded"
    assert turn["response"].startswith("Өнөөдөр Улаанбаатар орчимд бороотой байна.")
    assert "70%" in turn["response"]


def test_call_then_weather(client, planner):
    planner.then(
        ("call_contact", {"contact_name": "Ээж", "confirmation_question": "Ээж рүү тань залгах уу?"}),
        ("get_weather", {"date": "2026-10-06"}),
    )
    turn = chat(client, "Ээж рүү залгаад дараа нь өнөөдрийн цаг агаарыг хэл.")
    assert turn["intent"] == "multi"
    assert turn["stage"] == "awaiting_confirmation"
    assert turn["actions"][1]["result"]["status"] == "succeeded"

    final = report(client, turn, [
        result("a1", "call_contact", "handed_off", "url_scheme"),
        result("a2", "get_weather", "succeeded", "backend"),
    ])
    assert final.startswith("За, Ээж рүү тань залгаж байна. Өнөөдөр Улаанбаатар орчимд")


def test_partial_failure_is_not_reported_as_success(client, planner):
    planner.then(
        ("create_alarm", {"fire_at": "2026-10-07T07:00:00+08:00", "timezone": TZ}),
        ("create_reminder", {"title": "Ажил руу гарах", "due_at": "2026-10-07T08:30:00+08:00", "timezone": TZ}),
    )
    turn = chat(client, "Маргааш өглөө 7 цагт сэрээгээд 8:30-д ажил руу гарахыг сануулаарай.")
    final = report(client, turn, [
        result("a1", "create_alarm", "succeeded"),
        result("a2", "create_reminder", "failed", code="EK_SAVE_FAILED"),
    ])
    assert final == "За, маргааш өглөө 7 цагт сэрүүлэг тавилаа. Сануулга үүсгэхэд асуудал гарлаа."


def test_history_lets_followups_reuse_the_day(client, planner):
    planner.then(("create_alarm", {"fire_at": "2026-10-07T08:00:00+08:00", "timezone": TZ}))
    planner.then(("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ}))
    first = chat(client, "Маргааш 8 цагт сэрээгээрэй.")
    chat(client, "Тэгээд 9 цагт ажилтайг сануулаарай.", first["conversation_id"])

    second_history = planner.histories[1]
    assert second_history[0].text == "Маргааш 8 цагт сэрээгээрэй."
    assert "2026-10-07T08:00:00+08:00" in second_history[1].text


# --- Voice endpoint ------------------------------------------------------------

def _wav(seconds: float = 0.5, amplitude: int = 8000) -> bytes:
    """16 kHz mono WAV with a 440 Hz tone (amplitude 0 = a muted microphone)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        n = int(16000 * seconds)
        w.writeframes(struct.pack(f"<{n}h", *(int(amplitude * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(n))))
    return buf.getvalue()


def test_voice_pipeline(client, planner, monkeypatch):
    monkeypatch.setattr(main_mod, "get_stt", lambda http: FakeSTT("Маргааш 9 цагт ажилтайг минь сануулаарай."))
    planner.then(("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ}))
    import json

    r = client.post(
        "/api/v1/assistant/voice",
        files={"audio": ("voice.wav", _wav(), "audio/wav")},
        data={"context": json.dumps(context())},
    )
    assert r.status_code == 200, r.text
    assert r.json()["transcript"] == "Маргааш 9 цагт ажилтайг минь сануулаарай."


def test_voice_rejects_non_wav(client, monkeypatch):
    import json

    r = client.post(
        "/api/v1/assistant/voice",
        files={"audio": ("voice.webm", b"x" * 5000, "audio/webm")},
        data={"context": json.dumps(context())},
    )
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "invalid_request"


def test_empty_transcript_gives_mongolian_stt_error(client, monkeypatch):
    import json

    monkeypatch.setattr(main_mod, "get_stt", lambda http: FakeSTT(""))
    r = client.post(
        "/api/v1/assistant/voice",
        files={"audio": ("voice.wav", _wav(), "audio/wav")},
        data={"context": json.dumps(context())},
    )
    assert r.status_code == 422
    assert r.json()["error"] == {
        "code": "stt_failed",
        "message": "Уучлаарай, сайн сонсогдсонгүй. Дахин хэлээд өгөөч.",
        "request_id": r.json()["error"]["request_id"],
    }


def test_missing_key_is_explained(client, monkeypatch):
    def boom():
        raise ProviderNotConfigured("no key")

    monkeypatch.setattr(main_mod, "get_llm", boom)
    r = client.post("/api/v1/assistant/chat", json={"text": "сайн уу", "context": context()})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_failed"


def test_direction_suffix_follows_vowel_harmony():
    from bekhi_api.compose import toward

    assert toward("Ээж") == "Ээж рүү"
    assert toward("Бат") == "Бат руу"
    assert toward("Баатар") == "Баатар луу"
    assert toward("Сүхбаатарын талбай") == "Сүхбаатарын талбай руу"
    assert toward("Өлзий") == "Өлзий рүү"
    assert toward("Билгүүн") == "Билгүүн рүү"


async def test_overloaded_model_falls_back_to_next():
    from google.genai import errors, types

    from bekhi_api.providers.gemini import generate_with_fallback

    calls = []

    class Models:
        async def generate_content(self, model, contents, config):
            calls.append((model, config.thinking_config.thinking_level.value))
            if model == "busy":
                raise errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
            return "ok"

    class Client:
        class aio:
            models = Models()

    config = types.GenerateContentConfig(temperature=0)
    assert await generate_with_fallback(Client, ["busy", "free-lite"], contents="x", config=config) == "ok"
    assert calls == [("busy", "LOW"), ("free-lite", "MINIMAL")]


# --- Duudlaga STT / ElevenLabs TTS ------------------------------------------------

async def test_duudlaga_stt_request_and_errors():
    import httpx

    from bekhi_api.providers.base import ProviderUserError
    from bekhi_api.providers.duudlaga import DuudlagaSpeechToText

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        seen["multipart"] = b'name="file"' in request.content
        if seen.get("mode") == "credits":
            return httpx.Response(402, json={"error": {"code": "insufficient_credits", "message": "x"}})
        if seen.get("mode") == "silence":
            return httpx.Response(422, json={"error": {"code": "no_speech", "message": "x"}})
        return httpx.Response(200, json={"id": "tr_1", "text": "Маргааш 9 цагт сануулаарай.", "duration_seconds": 2.1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        stt = DuudlagaSpeechToText(http, "dk_test_key", "https://api.duudlaga.dev")
        assert await stt.transcribe(_wav(), "audio/wav") == "Маргааш 9 цагт сануулаарай."
        assert seen["auth"] == "Bearer dk_test_key"
        assert seen["url"] == "https://api.duudlaga.dev/v1/stt/transcriptions"
        assert seen["multipart"]

        seen["mode"] = "silence"
        assert await stt.transcribe(_wav(), "audio/wav") == ""

        seen["mode"] = "credits"
        try:
            await stt.transcribe(_wav(), "audio/wav")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "кредит" in e.message_mn


def test_tts_endpoint_returns_audio_and_caches(client, monkeypatch):
    calls = []

    class FakeTTS:
        media_type = "audio/mpeg"

        async def synthesize(self, text, voice=None):
            calls.append(text)
            return b"ID3fake-mp3"

    monkeypatch.setattr(main_mod, "get_tts", lambda http: FakeTTS())
    for _ in range(2):
        r = client.post("/api/v1/assistant/tts", json={"text": "За, болиулчихлаа."})
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/mpeg"
        assert r.content == b"ID3fake-mp3"
    assert calls == ["За, болиулчихлаа."]


def test_tts_says_the_app_name_as_a_word(client, monkeypatch):
    said = []

    class FakeTTS:
        async def synthesize(self, text, voice=None):
            said.append(text)
            return b"ID3fake-mp3"

    monkeypatch.setattr(main_mod, "get_tts", lambda http: FakeTTS())
    r = client.post("/api/v1/assistant/tts", json={"text": "Сайн байна уу, би БЭХИ байна. БЭХИ-д хэлээрэй."})
    assert r.status_code == 200
    assert said == ["Сайн байна уу, би Бэхи байна. Бэхи-д хэлээрэй."]


def test_tts_without_key_is_explained(client, monkeypatch):
    def missing(http):
        raise ProviderNotConfigured("no key")

    monkeypatch.setattr(main_mod, "get_tts", missing)
    r = client.post("/api/v1/assistant/tts", json={"text": "Сайн уу"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "tts_failed"
    assert "API key" in r.json()["error"]["message"]


async def test_elevenlabs_request_shape():
    import json as _json

    import httpx

    from bekhi_api.providers.elevenlabs import ElevenLabsTextToSpeech

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers["xi-api-key"]
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, content=b"ID3mp3")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        tts = ElevenLabsTextToSpeech(http, "el_key", "RbMF2tQ1nCK38TfvNGLk", "eleven_v4_turbo")
        assert await tts.synthesize("Сайн байна уу") == b"ID3mp3"
    assert seen["path"] == "/v1/text-to-speech/RbMF2tQ1nCK38TfvNGLk"
    assert seen["key"] == "el_key"
    assert seen["body"]["model_id"] == "eleven_v4_turbo"
    assert seen["body"]["language_code"] == "mn"


async def test_provider_errors_name_the_real_cause():
    import httpx

    from bekhi_api.providers.base import ProviderUserError
    from bekhi_api.providers.duudlaga import DuudlagaSpeechToText
    from bekhi_api.providers.elevenlabs import ElevenLabsTextToSpeech

    def duudlaga(request):  # 402 with a body shape we do not recognise
        return httpx.Response(402, json={"detail": "Payment Required"})

    def eleven(request):
        return httpx.Response(400, json={"detail": {"code": "invalid_api_key", "message": "must be 51 characters"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(duudlaga)) as http:
        try:
            await DuudlagaSpeechToText(http, "k", "https://api.duudlaga.dev").transcribe(_wav(), "audio/wav")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "кредит" in e.message_mn

    async with httpx.AsyncClient(transport=httpx.MockTransport(eleven)) as http:
        try:
            await ElevenLabsTextToSpeech(http, "k", "v", "eleven_v4_turbo").synthesize("Сайн уу")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "API key буруу" in e.message_mn

    def no_tts_permission(request):  # restricted key without "Text to Speech" access
        return httpx.Response(401, json={"detail": {
            "code": "unauthorized", "status": "missing_permissions",
            "message": "The API key you used is missing the permission text_to_speech to execute this operation.",
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(no_tts_permission)) as http:
        try:
            await ElevenLabsTextToSpeech(http, "k", "v", "eleven_v4_turbo").synthesize("Сайн уу")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "Text to Speech" in e.message_mn


async def test_stt_falls_back_when_primary_fails():
    from bekhi_api.providers import FallbackSpeechToText
    from bekhi_api.providers.base import ProviderUserError

    class Broke:
        async def transcribe(self, audio, mime_type):
            raise ProviderUserError("кредит дууссан", "stt_failed")

    stt = FallbackSpeechToText(Broke(), FakeSTT("Wi-Fi асаа."), ("duudlaga", "gemini"))
    assert await stt.transcribe(b"x", "audio/wav") == "Wi-Fi асаа."


async def test_failed_account_is_skipped_for_a_while(monkeypatch):
    from bekhi_api import providers
    from bekhi_api.providers import FallbackSpeechToText
    from bekhi_api.providers.base import ProviderUserError

    monkeypatch.setattr(providers, "_skip_until", {})
    calls = []

    class Broke:
        async def transcribe(self, audio, mime_type):
            calls.append("duudlaga")
            raise ProviderUserError("кредит дууссан", "stt_failed")

    for _ in range(3):
        stt = FallbackSpeechToText(Broke(), FakeSTT("Сайн уу"), ("duudlaga", "gemini"))
        assert await stt.transcribe(b"x", "audio/wav") == "Сайн уу"
    assert calls == ["duudlaga"]  # no more round trips to the provider with no credits


async def test_tts_falls_back_when_primary_fails(monkeypatch):
    from bekhi_api import providers
    from bekhi_api.providers import FallbackTextToSpeech
    from bekhi_api.providers.base import ProviderUserError

    monkeypatch.setattr(providers, "_skip_until", {})

    class BadKey:
        async def synthesize(self, text, voice=None):
            raise ProviderUserError("ElevenLabs API key буруу", "tts_failed")

    class Wav:
        async def synthesize(self, text, voice=None):
            return _wav()

    tts = FallbackTextToSpeech(BadKey(), Wav(), ("elevenlabs", "gemini"))
    assert (await tts.synthesize("Сайн уу"))[:4] == b"RIFF"


def test_only_the_configured_provider_is_used(monkeypatch):
    from bekhi_api.providers import FallbackTextToSpeech, _with_fallback

    def build(name):
        if name == "elevenlabs":
            raise ProviderNotConfigured("no key")
        return name

    assert _with_fallback("elevenlabs", "gemini", build, FallbackTextToSpeech) == "gemini"
    assert _with_fallback("gemini", None, build, FallbackTextToSpeech) == "gemini"
    try:
        _with_fallback("elevenlabs", None, build, FallbackTextToSpeech)
        raise AssertionError("expected ProviderNotConfigured")
    except ProviderNotConfigured:
        pass


def test_tts_endpoint_labels_wav_audio(client, monkeypatch):
    class WavTTS:
        async def synthesize(self, text, voice=None):
            return _wav()

    monkeypatch.setattr(main_mod, "get_tts", lambda http: WavTTS())
    r = client.post("/api/v1/assistant/tts", json={"text": "Gemini хоолой"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"


class _FakeLiveSession:
    def __init__(self, owner, messages):
        self.owner, self.messages = owner, messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_realtime_input(self, **kwargs):
        self.owner.sent.append(next(iter(kwargs)))

    async def receive(self):
        for m in self.messages:
            yield m


def _gemini_stub(live_messages=None, live_error=None, text="prompted"):
    from google.genai import types

    class Stub:
        sent: list[str] = []
        prompted: list[types.GenerateContentConfig] = []

        class aio:
            class live:
                @staticmethod
                def connect(model, config):
                    assert config.input_audio_transcription.language_codes == ["mn-MN"]
                    if live_error:
                        raise live_error
                    return _FakeLiveSession(Stub, live_messages or [])

            class models:
                @staticmethod
                async def generate_content(model, contents, config):
                    Stub.prompted.append(config)
                    return types.GenerateContentResponse(
                        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))]
                    )

    return Stub


async def test_gemini_stt_uses_the_transcription_model():
    from google.genai import types

    from bekhi_api.providers.gemini import GeminiSpeechToText

    msg = lambda **sc: types.LiveServerMessage(server_content=types.LiveServerContent(**sc))  # noqa: E731
    client = _gemini_stub([
        msg(input_transcription=types.Transcription(text="Сайн байна уу? Чи хэн бэ?")),
        msg(generation_complete=True),
    ])
    stt = GeminiSpeechToText(client, ["gemini-3.6-flash"], "gemini-3.5-transcribe-live")
    assert await stt.transcribe(_wav(), "audio/wav") == "Сайн байна уу? Чи хэн бэ?"
    assert client.sent[0] == "activity_start" and client.sent[-1] == "activity_end"
    assert client.prompted == []


async def test_gemini_stt_falls_back_to_prompted_transcription():
    from bekhi_api.providers.gemini import STT_INSTRUCTION, GeminiSpeechToText

    client = _gemini_stub(live_error=RuntimeError("quota"), text="Өнөөдөр бороо орох уу?")
    stt = GeminiSpeechToText(client, ["gemini-3.6-flash"], "gemini-3.5-transcribe-live")
    assert await stt.transcribe(_wav(), "audio/wav") == "Өнөөдөр бороо орох уу?"
    assert client.prompted[0].system_instruction == STT_INSTRUCTION


async def test_quota_exhausted_model_is_tried_last(monkeypatch):
    from google.genai import errors, types

    from bekhi_api.providers import gemini

    monkeypatch.setattr(gemini, "_quota_exhausted_until", {})
    calls = []

    class Models:
        async def generate_content(self, model, contents, config):
            calls.append(model)
            if model == "daily-limit":
                raise errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
            return "ok"

    class Client:
        class aio:
            models = Models()

    config = types.GenerateContentConfig(temperature=0)
    for _ in range(2):
        assert await gemini.generate_with_fallback(Client, ["daily-limit", "other"], contents="x", config=config) == "ok"
    assert calls == ["daily-limit", "other", "other"]


def test_every_function_restates_the_request():
    from bekhi_api.planner import SUMMARY_FIELD, function_specs

    for spec in function_specs():
        assert spec.parameters["required"][0] == SUMMARY_FIELD, spec.name
        assert SUMMARY_FIELD in spec.parameters["properties"], spec.name


def test_restated_question_is_returned_and_not_sent_as_tool_args(client, planner):
    planner.then(("reply", {"user_request": "Чи хэн бэ?", "text": "Би Дууд, таны туслах."}))
    turn = chat(client, "Сайн байна уу чихэн бэ")
    assert turn["transcript"] == "Сайн байна уу чихэн бэ"
    assert turn["summary"] == "Чи хэн бэ?"
    assert turn["response"] == "Би Дууд, таны туслах."

    planner.then(("create_reminder", {
        "user_request": "Маргааш 9 цагт ажилтай гэж сануулах",
        "title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00", "timezone": TZ,
    }))
    turn = chat(client, "Маргааш 9 цагт ажилтайг минь сануулаарай.")
    assert turn["summary"] == "Маргааш 9 цагт ажилтай гэж сануулах"
    assert "user_request" not in turn["actions"][0]["arguments"]


async def test_duudlaga_string_error_code():
    import httpx

    from bekhi_api.providers.base import ProviderUserError
    from bekhi_api.providers.duudlaga import DuudlagaSpeechToText

    def handler(request):  # the body Duudlaga actually sends with an empty balance
        return httpx.Response(402, json={"error": "insufficient_credits", "message": "Top up your balance."})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        try:
            await DuudlagaSpeechToText(http, "k", "https://api.duudlaga.dev").transcribe(_wav(), "audio/wav")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "кредит" in e.message_mn


async def test_library_voice_on_free_plan_is_explained():
    import httpx

    from bekhi_api.providers.base import ProviderUserError
    from bekhi_api.providers.elevenlabs import ElevenLabsTextToSpeech

    def handler(request):
        return httpx.Response(402, json={"detail": {
            "type": "payment_required", "code": "paid_plan_required",
            "message": "Free users cannot use library voices via the API.",
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        try:
            await ElevenLabsTextToSpeech(http, "k", "RbMF2tQ1nCK38TfvNGLk", "eleven_v4_turbo").synthesize("Сайн уу")
            raise AssertionError("expected ProviderUserError")
        except ProviderUserError as e:
            assert "ELEVENLABS_VOICE_ID" in e.message_mn


def test_muted_microphone_is_explained_without_calling_stt(client, monkeypatch):
    calls = []

    class CountingSTT(FakeSTT):
        async def transcribe(self, audio, mime_type):
            calls.append(1)
            return "x"

    monkeypatch.setattr(main_mod, "get_stt", lambda http: CountingSTT("x"))
    r = client.post("/api/v1/assistant/transcribe", files={"audio": ("v.wav", _wav(2, amplitude=0), "audio/wav")})
    assert r.status_code == 422
    assert "Микрофон" in r.json()["error"]["message"]
    assert calls == []


def test_contact_outcomes_from_the_phone_are_explained(client, planner):
    def plan_call():
        planner.then(("call_contact", {"user_request": "Бат руу залгах", "contact_name": "Бат",
                                       "confirmation_question": "Бат руу залгах уу?"}))
        return chat(client, "Бат руу залга")

    cases = [
        (result("a1", "call_contact", "handed_off", via="url_scheme"), "Бат руу тань залгаж байна"),
        (result("a1", "call_contact", "failed", via="react_native", code="CONTACT_NOT_FOUND"), "Бат гэсэн контакт олдсонгүй."),
        ({**result("a1", "call_contact", "needs_clarification", via="react_native", code="CONTACT_AMBIGUOUS"), "match_count": 3},
         "Бат гэсэн 3 контакт байна"),
    ]
    for outcome, expected in cases:
        assert expected in report(client, plan_call(), [outcome])


def test_message_sheet_outcomes(client, planner):
    def plan_message():
        planner.then(("send_message", {"user_request": "Батад мессеж бичих", "contact_name": "Бат", "body": "Орой уулзъя",
                                       "confirmation_question": "Батад 'Орой уулзъя' гэж бичих үү?"}))
        return chat(client, "Батад орой уулзъя гэж бич")

    assert "мессеж явууллаа" in report(client, plan_message(), [result("a1", "send_message", "succeeded", via="react_native")])
    assert "Илгээх товчийг" in report(client, plan_message(), [result("a1", "send_message", "handed_off", via="react_native")])
    assert "мессеж илгээх боломжгүй" in report(
        client, plan_message(), [result("a1", "send_message", "unsupported", via=None, code="SMS_UNAVAILABLE")]
    )



def test_notification_outcomes_are_honest(client, planner):
    def plan(tool, args, text):
        planner.then((tool, {"user_request": text, **args, "timezone": TZ}))
        return chat(client, text)

    alarm = plan("create_alarm", {"fire_at": "2026-10-07T07:00:00+08:00"}, "Өглөө 7 цагт сэрээгээрэй")
    said = report(client, alarm, [result("a1", "create_alarm", "succeeded", via="react_native")])
    assert "мэдэгдлээр сэрээнэ" in said and "сэрүүлэг тавилаа" not in said

    event = plan("create_calendar_event", {"title": "Уулзалт", "start_at": "2026-10-07T15:00:00+08:00"}, "Маргааш 3 цагт уулзалт нэм")
    assert "Календарьт шууд нэмж чадахгүй" in report(client, event, [result("a1", "create_calendar_event", "succeeded", via="react_native")])

    reminder = plan("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00"}, "Маргааш 9 цагт сануул")
    assert "сануулъя" in report(client, reminder, [result("a1", "create_reminder", "succeeded", via="react_native")])

    reminder = plan("create_reminder", {"title": "Ажилтай", "due_at": "2026-10-07T09:00:00+08:00"}, "Маргааш 9 цагт сануул")
    denied = report(client, reminder, [result("a1", "create_reminder", "permission_denied", via="react_native", code="NOTIFICATIONS_DENIED")])
    assert "Notifications" in denied


def test_voices_and_paid_voice_fallback(client, monkeypatch):
    from bekhi_api.providers.base import VoiceNeedsPaidPlan

    asked = []

    class Eleven:
        async def synthesize(self, text, voice=None):
            asked.append(voice)
            if voice == "WgH4JH8sD6a2SIrujiKn":  # Sarnai: Voice Library, free plan
                raise VoiceNeedsPaidPlan(voice)
            return b"ID3" + (voice or "default").encode()

    monkeypatch.setattr(main_mod, "get_tts", lambda http: Eleven())
    listed = client.get("/api/v1/assistant/voices").json()
    names = {v["name"]: v for v in listed["voices"]}
    assert not names["Laura"]["needs_paid_plan"] and names["Sarnai (Монгол)"]["needs_paid_plan"]

    r = client.post("/api/v1/assistant/tts", json={"text": "Сайн уу", "voice": "FGY2WhTYpPnrIDTdsKH5"})
    assert r.content == b"ID3FGY2WhTYpPnrIDTdsKH5" and "x-bekhi-voice-fallback" not in r.headers

    r = client.post("/api/v1/assistant/tts", json={"text": "Сайн уу", "voice": "WgH4JH8sD6a2SIrujiKn"})
    assert r.content == b"ID3default" and r.headers["x-bekhi-voice-fallback"] == "paid_plan_required"

    r = client.post("/api/v1/assistant/tts", json={"text": "Сайн уу", "voice": "not-a-listed-voice"})
    assert r.content == b"ID3default"  # unknown ids never reach the provider
    assert "not-a-listed-voice" not in asked
