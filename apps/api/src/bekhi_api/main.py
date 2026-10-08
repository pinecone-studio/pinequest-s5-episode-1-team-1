"""BEKHI FastAPI app.

Endpoints (Phase 3/4):
  GET  /api/v1/health
  POST /api/v1/assistant/chat              text -> AssistantTurn
  POST /api/v1/assistant/voice             16 kHz mono WAV + context -> AssistantTurn
  POST /api/v1/assistant/transcribe        16 kHz mono WAV -> transcript
  POST /api/v1/assistant/tts               Mongolian text -> speech (MP3, or WAV from the fallback)
  POST /api/v1/assistant/actions/results   device outcomes -> final Mongolian answer
  POST /api/v1/maps/directions             phone location + destination -> route (Google Routes API)
"""

from __future__ import annotations

import io
import logging
import math
import time
import uuid
import wave
from array import array
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from . import desktop, directions
from .config import ELEVENLABS_VOICES, get_settings
from .contracts import apply_defaults, tool_manifest, validate_tool_args
from .models import (
    ActionResultsRequest,
    ActionResultsResponse,
    ApiError,
    ApiErrorBody,
    AssistantContext,
    AssistantTurn,
    ChatRequest,
    DirectionsRequest,
    DirectionsResponse,
)
from .compose import speakable
from .pipeline import ContractViolation, Deps, UnknownTurn, plan_turn, report_results
from .providers import ProviderNotConfigured, ProviderUserError, VoiceNeedsPaidPlan, get_llm, get_search, get_stt, get_tts
from .store import MemoryStore

log = logging.getLogger("bekhi_api")

MN_STT_FAILED = "Уучлаарай, сайн сонсогдсонгүй. Дахин хэлээд өгөөч."
MN_MIC_SILENT = "Бичлэгт дуу огт алга байна. Микрофон тань дуугүй (mute) болсон эсэхийг шалгана уу."
MN_AI_FAILED = "Уучлаарай, одоогоор ойлгоход асуудал гарлаа."
MN_NOT_CONFIGURED = "Gemini API key тохируулаагүй байна (apps/api/.env)."
MN_KEY_MISSING = "{} API key тохируулаагүй байна (apps/api/.env)."
PROVIDER_NAMES = {"gemini": "Gemini", "duudlaga": "Duudlaga", "elevenlabs": "ElevenLabs"}
MN_TTS_FAILED = "Уучлаарай, хариуг дуугаар уншихад алдаа гарлаа."
MN_INVALID = "Хүсэлт буруу байна."
MN_RATE_LIMITED = "Хэт олон хүсэлт ирлээ. Түр хүлээгээд дахин оролдоно уу."
MN_INTERNAL = "Уучлаарай, системд алдаа гарлаа."
MN_DESKTOP_UNAVAILABLE = "Энэ компьютер дээр үйлдэл хийх боломжгүй."
MN_DIRECTIONS = {
    "ROUTE_NOT_FOUND": (404, "Тэр газар хүрэх зам олдсонгүй. Хаягаа тодруулаад дахин оролдоно уу."),
    "MAPS_KEY_INVALID": (502, "Google Maps API key буруу, эсвэл Routes API идэвхжээгүй байна."),
    "MAPS_FAILED": (502, "Уучлаарай, зам тооцоолоход алдаа гарлаа."),
}
# Billed per request, so these share the assistant's per-minute limit.
RATE_LIMITED_PATHS = ("/api/v1/assistant", "/api/v1/maps")
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

WAV_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
# Set on a TTS response read in the default voice because the chosen one needs a paid plan.
VOICE_FALLBACK_HEADER = "X-Bekhi-Voice-Fallback"
# Quieter than this at its loudest, a recording has no voice in it: a muted or wrong microphone.
# Speech peaks around -30..-5 dBFS; a muted mic gives about -90.
SILENT_PEAK_DBFS = -60
TTS_CACHE_MAX = 64  # repeated phrases ("За, болиулчихлаа.") are not re-billed


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    # An id from GET /assistant/voices; anything else means the default voice.
    voice: str | None = Field(default=None, max_length=64)


class DesktopActionRequest(BaseModel):
    tool: str = Field(max_length=64)
    arguments: dict


def _is_local(request: Request) -> bool:
    """Desktop actions run on this PC, so only this PC may ask for them (not the phone or the LAN)."""
    return bool(request.client) and request.client.host in LOCAL_HOSTS


class ApiException(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def _audio_levels(data: bytes) -> tuple[str, float | None]:
    """Length and loudness of an upload, for diagnosing "it did not hear me" (never the content).
    Returns a log line and the peak level in dBFS. voiced = time in 20 ms frames louder than
    -40 dBFS, roughly how much speech was captured."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate, channels, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return "audio unreadable", None
    if width != 2 or not frames:
        return f"audio {rate}Hz ch={channels} width={width}", None
    samples = array("h", frames)
    db = lambda x: 20 * math.log10(max(x, 1) / 32768)  # noqa: E731
    step = max(1, rate * channels // 50)
    loud = sum(
        1
        for i in range(0, len(samples), step)
        if db(math.sqrt(sum(v * v for v in samples[i : i + step]) / len(samples[i : i + step]))) > -40
    )
    peak = db(max(abs(min(samples)), max(samples)))
    line = f"audio {len(samples) / channels / rate:.1f}s {rate}Hz ch={channels} peak={peak:.0f}dBFS voiced={loud * 0.02:.1f}s"
    return line, peak


def _audio_media_type(audio: bytes) -> str:
    """ElevenLabs returns MP3, the Gemini fallback WAV."""
    return "audio/wav" if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE" else "audio/mpeg"


def _error(status: int, code: str, message: str, request: Request) -> JSONResponse:
    body = ApiError(error=ApiErrorBody(code=code, message=message, request_id=getattr(request.state, "request_id", None)))
    return JSONResponse(status_code=status, content=body.model_dump())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=10) as http:
        app.state.http = http
        app.state.store = MemoryStore()
        app.state.desktop = None
        if get_settings().desktop_actions and desktop.available():
            app.state.desktop = desktop.DesktopScheduler()
            app.state.desktop.start()
        try:
            yield
        finally:
            if app.state.desktop:
                await app.state.desktop.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(title="BEKHI API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=[VOICE_FALLBACK_HEADER],
    )

    hits: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        if request.url.path.startswith(RATE_LIMITED_PATHS):
            key = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window = hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= settings.rate_limit_per_minute:
                return _error(429, "rate_limited", MN_RATE_LIMITED, request)
            window.append(now)
        start = time.perf_counter()
        response = await call_next(request)
        # Safe logging: method, path, status, latency. Never bodies, audio or transcripts.
        log.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000, request.state.request_id)
        return response

    @app.exception_handler(ApiException)
    async def _api_exc(request: Request, exc: ApiException):
        return _error(exc.status, exc.code, exc.message, request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _error(422, "invalid_request", MN_INVALID, request)

    def deps(request: Request) -> Deps:
        try:
            llm = get_llm()
        except ProviderNotConfigured as e:
            log.error("llm not configured: %s", e)
            raise ApiException(503, "llm_failed", MN_NOT_CONFIGURED) from e
        http = request.app.state.http
        return Deps(llm=llm, http=http, store=request.app.state.store, search=get_search(http))

    async def run_plan(text: str, ctx: AssistantContext, request: Request) -> AssistantTurn:
        d = deps(request)
        try:
            return await plan_turn(text, ctx, d)
        except ContractViolation as e:
            raise ApiException(500, "internal", MN_AI_FAILED) from e
        except ApiException:
            raise
        except Exception as e:  # provider/network errors
            log.exception("planning failed rid=%s", request.state.request_id)
            raise ApiException(502, "llm_failed", MN_AI_FAILED) from e

    async def transcribe(audio: UploadFile, request: Request) -> str:
        if (audio.content_type or "").split(";")[0].strip().lower() not in WAV_TYPES:
            raise ApiException(415, "invalid_request", MN_INVALID)
        data = await audio.read(settings.max_audio_bytes + 1)
        if len(data) > settings.max_audio_bytes or len(data) < 1000:
            raise ApiException(413 if len(data) > 1000 else 422, "invalid_request", MN_STT_FAILED)
        try:
            stt = get_stt(request.app.state.http)
        except ProviderNotConfigured as e:
            raise ApiException(503, "stt_failed", MN_KEY_MISSING.format(PROVIDER_NAMES.get(settings.stt_provider, settings.stt_provider))) from e
        levels, peak = _audio_levels(data)
        log.info("%s rid=%s", levels, request.state.request_id)
        if peak is not None and peak < SILENT_PEAK_DBFS:
            # Nothing to recognise; do not pay the STT provider to say so.
            raise ApiException(422, "stt_failed", MN_MIC_SILENT)
        start = time.perf_counter()
        try:
            text = await stt.transcribe(data, "audio/wav")
            log.info("stt %.0fms heard=%s rid=%s", (time.perf_counter() - start) * 1000, bool(text), request.state.request_id)
        except ProviderUserError as e:
            raise ApiException(502, "stt_failed", e.message_mn) from e
        except Exception as e:
            log.exception("stt failed rid=%s", request.state.request_id)
            raise ApiException(502, "stt_failed", MN_STT_FAILED) from e
        finally:
            del data  # raw audio is never stored
        if not text:
            raise ApiException(422, "stt_failed", MN_STT_FAILED)
        return text[:2000]

    @app.get("/api/v1/health")
    async def health():
        keys = {
            "gemini": settings.gemini_api_key,
            "duudlaga": settings.duudlaga_api_key,
            "elevenlabs": settings.elevenlabs_api_key,
        }

        def speech(provider: str, fallback: str | None) -> dict:
            return {
                "provider": provider,
                "configured": bool(keys.get(provider)),
                "fallback": fallback,
                "fallback_configured": bool(fallback and keys.get(fallback)),
            }

        return {
            "status": "ok",
            "llm": {"provider": settings.llm_provider, "configured": settings.llm_configured, "model": settings.gemini_model},
            "stt": speech(settings.stt_provider, settings.stt_fallback_provider),
            "tts": speech(settings.tts_provider, settings.tts_fallback_provider),
            "search": {
                "provider": settings.web_search_provider,
                "configured": bool({"tavily": settings.tavily_api_key, "gemini": settings.gemini_api_key}.get(settings.web_search_provider or "")),
            },
            "maps": {"provider": "google_routes", "configured": bool(settings.google_maps_api_key)},
        }

    @app.post("/api/v1/assistant/chat", response_model=AssistantTurn)
    async def chat(body: ChatRequest, request: Request):
        return await run_plan(body.text.strip(), body.context, request)

    @app.post("/api/v1/assistant/voice", response_model=AssistantTurn)
    async def voice(request: Request, audio: UploadFile = File(...), context: str = Form(...)):
        try:
            ctx = AssistantContext.model_validate_json(context)
        except ValidationError as e:
            raise ApiException(422, "invalid_request", MN_INVALID) from e
        text = await transcribe(audio, request)
        return await run_plan(text, ctx, request)

    @app.post("/api/v1/assistant/transcribe")
    async def transcribe_only(request: Request, audio: UploadFile = File(...)):
        return {"transcript": await transcribe(audio, request)}

    tts_cache: dict[tuple[str | None, str], tuple[bytes, bool]] = {}
    voice_ids = {v.id for v in ELEVENLABS_VOICES}
    needs_paid_plan: set[str] = {v.id for v in ELEVENLABS_VOICES if v.paid}

    @app.get("/api/v1/assistant/voices")
    async def voices():
        """Voices the app can choose from; `default` is used when none is chosen."""
        return {
            "default": settings.elevenlabs_voice_id,
            "voices": [
                {"id": v.id, "name": v.name, "gender": v.gender, "needs_paid_plan": v.id in needs_paid_plan}
                for v in ELEVENLABS_VOICES
            ],
        }

    @app.post("/api/v1/assistant/tts")
    async def tts(body: TtsRequest, request: Request):
        text = speakable(body.text.strip())
        voice = body.voice if body.voice in voice_ids and body.voice != settings.elevenlabs_voice_id else None
        cached = tts_cache.get((voice, text))
        if cached is None:
            try:
                engine = get_tts(request.app.state.http)
            except ProviderNotConfigured as e:
                raise ApiException(503, "tts_failed", MN_KEY_MISSING.format(PROVIDER_NAMES.get(settings.tts_provider, settings.tts_provider))) from e
            try:
                try:
                    cached = (await engine.synthesize(text, voice), False)
                except VoiceNeedsPaidPlan:
                    # Still speak, in the default voice; the app tells the user why.
                    needs_paid_plan.add(voice or "")
                    cached = (await engine.synthesize(text), True)
            except ProviderUserError as e:
                raise ApiException(502, "tts_failed", e.message_mn) from e
            except Exception as e:
                log.exception("tts failed rid=%s", request.state.request_id)
                raise ApiException(502, "tts_failed", MN_TTS_FAILED) from e
            if len(tts_cache) >= TTS_CACHE_MAX:
                tts_cache.pop(next(iter(tts_cache)))
            tts_cache[(voice, text)] = cached
        audio, fell_back = cached
        headers = {"Cache-Control": "no-store"}
        if fell_back:
            headers[VOICE_FALLBACK_HEADER] = "paid_plan_required"
        return Response(content=audio, media_type=_audio_media_type(audio), headers=headers)

    @app.post("/api/v1/desktop/actions")
    async def desktop_action(body: DesktopActionRequest, request: Request):
        """The web app on this Windows PC: run a device action here (reminder, alarm, note...)."""
        scheduler = request.app.state.desktop
        if scheduler is None or not _is_local(request):
            raise ApiException(404, "invalid_request", MN_DESKTOP_UNAVAILABLE)
        if body.tool not in tool_manifest():
            raise ApiException(422, "invalid_request", MN_INVALID)
        args = apply_defaults(body.tool, body.arguments)
        if validate_tool_args(body.tool, args):
            raise ApiException(422, "invalid_request", MN_INVALID)
        try:
            return desktop.run(body.tool, args, scheduler)
        except Exception:
            log.exception("desktop action failed rid=%s", request.state.request_id)
            return {"status": "failed", "executed_via": "backend", "error_code": "DESKTOP_FAILED"}

    @app.post("/api/v1/assistant/actions/results", response_model=ActionResultsResponse)
    async def action_results(body: ActionResultsRequest, request: Request):
        # Outcome codes only (never names, numbers or text): what happened on the device.
        for r in body.results:
            log.info("action %s %s %s rid=%s", r.tool, r.status, r.error_code or "-", request.state.request_id)
        try:
            return report_results(body, request.app.state.store)
        except UnknownTurn as e:
            raise ApiException(404, "invalid_request", MN_INVALID) from e

    @app.post("/api/v1/maps/directions", response_model=DirectionsResponse)
    async def maps_directions(body: DirectionsRequest, request: Request):
        if not settings.google_maps_api_key:
            raise ApiException(503, "maps_failed", MN_KEY_MISSING.format("Google Maps"))
        try:
            return await directions.compute_route(
                request.app.state.http,
                settings.google_maps_api_key,
                body.origin.model_dump(),
                body.destination.strip(),
                body.mode,
            )
        except directions.DirectionsError as e:
            status, message = MN_DIRECTIONS[e.code]
            raise ApiException(status, "maps_failed", message) from e
        except httpx.HTTPError as e:
            log.warning("routes api unreachable: %s rid=%s", type(e).__name__, request.state.request_id)
            status, message = MN_DIRECTIONS["MAPS_FAILED"]
            raise ApiException(status, "maps_failed", message) from e

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("bekhi_api.main:app", host="0.0.0.0", port=8000, reload=False)
