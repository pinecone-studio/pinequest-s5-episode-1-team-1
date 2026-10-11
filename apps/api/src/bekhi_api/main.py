"""BEKHI FastAPI app.

Endpoints (Phase 3/4):
  GET  /api/v1/health
  POST /api/v1/assistant/chat              text -> AssistantTurn
  POST /api/v1/assistant/voice             16 kHz mono WAV + context -> AssistantTurn
  POST /api/v1/assistant/transcribe        16 kHz mono WAV -> transcript
  POST /api/v1/assistant/tts               Mongolian text -> speech (MP3, or WAV from the fallback)
  POST /api/v1/assistant/actions/results   device outcomes -> final Mongolian answer
  POST /api/v1/maps/directions             phone location + destination -> route (Google Routes API)
  POST /api/v1/sync/devices                this device is linked (sync code + device id headers)
  GET  /api/v1/sync/alarms                 alarms/timers to ring on every linked device
  POST /api/v1/sync/alarms                 publish one this device has set
  POST /api/v1/sync/alarms/cancel          cancel some on every linked device
  POST /api/v1/desktop/sync                link this computer (the API's own scheduler) to a sync code
"""

from __future__ import annotations

import asyncio
import html
import io
import ipaddress
import logging
import math
import time
import uuid
import wave
from array import array
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, ValidationError

from . import commands, desktop, directions, google_link, memory, sync, todos
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
    SyncAlarm,
    SyncCancelRequest,
    SyncDeviceRequest,
    SyncPublishResponse,
    SyncPullResponse,
)
from .compose import speakable
from .pipeline import ContractViolation, Deps, UnknownTurn, plan_turn, report_results
from .providers import ProviderNotConfigured, ProviderUserError, VoiceNeedsPaidPlan, get_llm, get_search, get_stt, get_tts
from .store import MemoryStore

log = logging.getLogger("bekhi_api")

MN_STT_FAILED = "Уучлаарай, сайн сонсогдсонгүй. Дахин хэлээд өгөөч."
MN_MIC_SILENT = "Бичлэгт дуу огт алга байна. Микрофон тань дуугүй (mute) болсон эсэхийг шалгана уу."
MN_AI_FAILED = "Уучлаарай, одоогоор ойлгоход асуудал гарлаа."
MN_AI_BUSY = "Одоо хэт олон хүсэлт ирж байна. Түр хүлээгээд дахин асуугаарай."
# The app waits 30 s for an answer; a turn that would take longer is stopped first, with a clear reply.
PLAN_TIMEOUT_SECONDS = 27
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
# Billed per request, so these share the assistant's per-minute limit. Sync too: a sync code
# must not be guessable by trying many.
RATE_LIMITED_PATHS = ("/api/v1/assistant", "/api/v1/maps", "/api/v1/sync")
MN_SYNC_CODE_INVALID = "Холбох код буруу байна."
MN_SYNC_FAILED = "Бусад төхөөрөмжтэй холбогдож чадсангүй."
MN_GOOGLE_UNAVAILABLE = "Gmail холболт энэ сервер дээр тохируулагдаагүй байна."
MN_GOOGLE_FROM_PC = "Gmail-ийг компьютер дээрх БЭХИ-ээс холбоно уу. Холбогдсоны дараа утсан дээр ч ажиллана."
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

WAV_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
# Set on a TTS response read in the default voice because the chosen one needs a paid plan.
VOICE_FALLBACK_HEADER = "X-Bekhi-Voice-Fallback"
# The device-linking sync code (packages/contracts sync.ts), also sent with chat and voice requests.
SYNC_CODE_HEADER = "X-Bekhi-Sync"
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


class DesktopSyncRequest(BaseModel):
    code: str = Field(max_length=32)
    # The user typed this code to join it. Otherwise a browser opening BEKHI on a computer that is
    # already linked joins the computer's code, rather than taking the computer over.
    replace: bool = False


class SendCommandRequest(BaseModel):
    target: Literal["computer", "phone"]
    tool: str = Field(max_length=64)
    arguments: dict


class CommandOutcome(BaseModel):
    status: str = Field(max_length=32)
    executed_via: str | None = Field(default=None, max_length=32)
    error_code: str | None = Field(default=None, max_length=64)
    data: dict | None = None


def _google_redirect(request: Request) -> str | None:
    """Google's callback on this API, as registered in Google Cloud: http://127.0.0.1:8000 on the user's
    PC, https on a public host. None from a LAN address (a phone on the PC's Wi-Fi), which Google refuses."""
    host = request.url.hostname or ""
    if host in LOCAL_HOSTS:
        return f"http://127.0.0.1:{request.url.port or 80}/api/v1/auth/google/callback"
    try:
        if not ipaddress.ip_address(host).is_global:
            return None
    except ValueError:
        pass
    return f"https://{host}/api/v1/auth/google/callback"


def _google_page(title: str, body: str, close: bool = False) -> HTMLResponse:
    script = "<script>setTimeout(function(){window.close()},2500)</script>" if close else ""
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>BEKHI</title><body style='font-family:system-ui,sans-serif;background:#05060b;color:#f2f4f8;"
        "display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;text-align:center'><div>"
        f"<h2>{html.escape(title)}</h2><p style='color:#a9b1bf'>{html.escape(body)}</p></div>{script}"
    )


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


class _AppFiles(StaticFiles):
    """The web app: any path that is not a file is one of its screens, so it gets index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or path.startswith("api"):
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=10) as http:
        app.state.http = http
        app.state.store = MemoryStore()
        settings = get_settings()
        app.state.sync = sync.make_store(settings.supabase_url, settings.supabase_service_role_key, http, settings.sync_api_url)
        app.state.todos = todos.make_store(settings.supabase_url, settings.supabase_service_role_key, http)
        app.state.memory = memory.make_store(settings.supabase_url, settings.supabase_service_role_key, http)
        app.state.commands = commands.CommandStore()
        # On the user's PC (agent.py): commands for a device not listening here go on to the cloud.
        app.state.remote_commands = commands.RemoteCommands(settings.sync_api_url, http) if settings.sync_api_url else None
        app.state.google = google_link.make(settings, http, on_pc=settings.desktop_actions and desktop.available(),
                                            data_dir=google_link.local_data_dir())
        if app.state.google is not None:  # a linked account's to-dos are its Google Tasks
            app.state.todos = todos.GoogleTasksTodoStore(app.state.google, app.state.todos)
        app.state.desktop = None
        if settings.desktop_actions and desktop.available():
            app.state.desktop = desktop.DesktopScheduler(
                sync=app.state.sync, commands=app.state.commands, remote_commands=app.state.remote_commands
            )
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
        # The cloud web app (a public site) may call a PC agent on 127.0.0.1 (agent.py).
        allow_private_network=settings.desktop_actions,
    )

    hits: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        # Waiting for commands is long polling: only sending them counts.
        polling = request.method == "GET" and request.url.path.startswith("/api/v1/sync/commands")
        if request.url.path.startswith(RATE_LIMITED_PATHS) and not polling:
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
        return Deps(
            llm=llm, http=http, store=request.app.state.store, search=get_search(http),
            todo_store=request.app.state.todos,
            memory_store=request.app.state.memory,
            on_pc=request.app.state.desktop is not None,
            google=request.app.state.google,
            # The asking device's sync code picks its account's to-do list (sync.py).
            account=sync.account_key(request.headers.get(SYNC_CODE_HEADER)),
        )

    async def run_plan(text: str, ctx: AssistantContext, request: Request) -> AssistantTurn:
        d = deps(request)
        try:
            async with asyncio.timeout(PLAN_TIMEOUT_SECONDS):
                return await plan_turn(text, ctx, d)
        except ContractViolation as e:
            raise ApiException(500, "internal", MN_AI_FAILED) from e
        except ApiException:
            raise
        except TimeoutError as e:
            log.warning("planning timed out rid=%s", request.state.request_id)
            raise ApiException(503, "llm_failed", MN_AI_BUSY) from e
        except Exception as e:  # provider/network errors
            if getattr(e, "code", None) == 429:  # every model out of quota, also after waiting
                log.warning("planning out of quota rid=%s", request.state.request_id)
                raise ApiException(503, "llm_failed", MN_AI_BUSY) from e
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
        """The web app on this computer: run a device action here (reminder, alarm, note...)."""
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

    @app.post("/api/v1/desktop/sync")
    async def desktop_sync(body: DesktopSyncRequest, request: Request):
        """The web app on this computer links the computer itself, so it rings synced alarms with the browser closed."""
        scheduler = request.app.state.desktop
        if scheduler is None or not _is_local(request):
            raise ApiException(404, "invalid_request", MN_DESKTOP_UNAVAILABLE)
        account = sync.account_key(body.code)
        if account is None:
            raise ApiException(401, "unauthorized", MN_SYNC_CODE_INVALID)
        current = scheduler.linked_code()
        if current and not body.replace and sync.account_key(current) != account:
            return {"device_id": scheduler.device_id, "code": current}
        # A PC agent pulls from the cloud, which takes the code itself (it stays on this PC).
        remote = isinstance(request.app.state.sync, sync.RemoteSyncStore)
        device_id = scheduler.link(body.code if remote else account, code=body.code)
        try:
            await scheduler.sync_now()
        except Exception:
            log.warning("desktop sync failed rid=%s", request.state.request_id)
        return {"device_id": device_id}

    def sync_identity(code: str | None, device: str | None) -> tuple[str, str]:
        account = sync.account_key(code)
        if account is None or not sync.valid_device_id(device):
            raise ApiException(401, "unauthorized", MN_SYNC_CODE_INVALID)
        return account, device or ""

    async def sync_call(request: Request, work):
        try:
            return await work(request.app.state.sync, datetime.now(timezone.utc))
        except httpx.HTTPError as e:
            log.warning("sync store failed: %s rid=%s", type(e).__name__, request.state.request_id)
            raise ApiException(502, "internal", MN_SYNC_FAILED) from e

    @app.post("/api/v1/sync/devices")
    async def sync_device(body: SyncDeviceRequest, request: Request,
                          x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, device = sync_identity(x_bekhi_sync, x_bekhi_device)
        await sync_call(request, lambda store, now: store.touch_device(account, device, body.platform, now))
        return {"ok": True}

    @app.get("/api/v1/sync/alarms", response_model=SyncPullResponse)
    async def sync_pull(request: Request, x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        active, cancelled = await sync_call(request, lambda store, now: store.pull(account, now))
        return {"active": active, "cancelled": cancelled}

    @app.post("/api/v1/sync/alarms", response_model=SyncPublishResponse)
    async def sync_publish(body: SyncAlarm, request: Request,
                           x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, device = sync_identity(x_bekhi_sync, x_bekhi_device)
        alarm = {"id": str(body.id), "kind": body.kind, "title": body.title, "fire_at": body.fire_at.isoformat()}

        async def publish(store, now):
            await store.publish(account, device, alarm)
            return await store.other_devices(account, device, now)

        return {"other_devices": await sync_call(request, publish)}

    @app.post("/api/v1/sync/alarms/cancel")
    async def sync_cancel(body: SyncCancelRequest, request: Request,
                          x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        ids = [str(i) for i in body.ids]
        await sync_call(request, lambda store, now: store.cancel(account, ids, now))
        return {"ok": True}

    @app.post("/api/v1/sync/commands")
    async def send_command(body: SendCommandRequest, request: Request,
                           x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        """Asks the user's other device (computer or phone) to do something; `id` null: none is listening."""
        account, device = sync_identity(x_bekhi_sync, x_bekhi_device)
        if body.tool not in commands.RELAYED_TOOLS[body.target]:
            raise ApiException(422, "invalid_request", MN_INVALID)
        args = apply_defaults(body.tool, body.arguments)
        if validate_tool_args(body.tool, args):
            raise ApiException(422, "invalid_request", MN_INVALID)
        cmd = request.app.state.commands.send(account, device, body.target, body.tool, args)
        if cmd is not None:
            return {"id": cmd.id}
        remote = request.app.state.remote_commands
        if remote is None:
            return {"id": None}
        try:
            remote_id = await remote.send(x_bekhi_sync or "", device, body.target, body.tool, args)
        except httpx.HTTPError as e:
            log.warning("command relay failed: %s rid=%s", type(e).__name__, request.state.request_id)
            return {"id": None}
        if remote_id:
            forwarded[remote_id] = account
        return {"id": remote_id}

    # Commands this API passed on to the cloud: their outcome is asked there.
    forwarded: dict[str, str] = {}

    @app.get("/api/v1/sync/commands/{command_id}")
    async def command_state(command_id: str, request: Request, wait: float = 0,
                            x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, device = sync_identity(x_bekhi_sync, x_bekhi_device)
        if forwarded.get(command_id) == account and request.app.state.remote_commands is not None:
            try:
                return await request.app.state.remote_commands.state(x_bekhi_sync or "", device, command_id, wait)
            except httpx.HTTPError as e:
                raise ApiException(502, "internal", MN_SYNC_FAILED) from e
        cmd = await request.app.state.commands.state(account, command_id, wait)
        if cmd is None:
            raise ApiException(404, "invalid_request", MN_INVALID)
        return {"state": cmd.state, "outcome": cmd.outcome}

    @app.get("/api/v1/sync/commands")
    async def take_commands(request: Request, target: Literal["computer", "phone"], wait: float = 0,
                            x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        """A device waits here for what the user's other devices ask of it."""
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        taken = await request.app.state.commands.take(account, target, wait)
        return {"commands": [c.wire() for c in taken]}

    @app.post("/api/v1/sync/commands/{command_id}/result")
    async def command_result(command_id: str, body: CommandOutcome, request: Request,
                             x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        log.info("command %s %s rid=%s", body.status, body.error_code or "-", request.state.request_id)
        if not request.app.state.commands.finish(account, command_id, body.model_dump()):
            raise ApiException(404, "invalid_request", MN_INVALID)
        return {"ok": True}

    def google_or_404(request: Request) -> google_link.Google:
        if request.app.state.google is None:
            raise ApiException(404, "invalid_request", MN_GOOGLE_UNAVAILABLE)
        return request.app.state.google

    @app.post("/api/v1/auth/google/start")
    async def google_start(request: Request, x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        """The Google sign-in page for linking Gmail to this account; the app opens `url`."""
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        google = google_or_404(request)
        redirect = _google_redirect(request)
        if redirect is None:
            raise ApiException(400, "invalid_request", MN_GOOGLE_FROM_PC)
        return {"url": google.start(account, redirect)}

    @app.get("/api/v1/auth/google/callback")
    async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
        google = google_or_404(request)
        if error or not code:
            return _google_page("Google холболт цуцлагдлаа.", "Дахин оролдохдоо БЭХИ дээр 'Gmail холбох' дарна уу.")
        try:
            email = await google.finish(state, code)
        except PermissionError:
            return _google_page("Холбож чадсангүй.", "Gmail унших зөвшөөрлийг тэмдэглээд дахин оролдоно уу.")
        except httpx.HTTPError:
            log.warning("google sign-in failed rid=%s", request.state.request_id)
            return _google_page("Холбож чадсангүй.", "Google-тэй холбогдоход алдаа гарлаа. Дахин оролдоно уу.")
        return _google_page(f"Google холбогдлоо: {email}",
                            "Gmail, Google Tasks бэлэн. Энэ цонхыг хаагаад БЭХИ-д 'Шинэ имэйл байна уу?' гэж асуугаарай.",
                            close=True)

    @app.get("/api/v1/auth/google")
    async def google_status(request: Request, x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        google = request.app.state.google
        return {"available": google is not None, **(await google.status(account) if google else {"linked": False, "email": None})}

    @app.post("/api/v1/auth/google/unlink")
    async def google_unlink(request: Request, x_bekhi_sync: str | None = Header(None), x_bekhi_device: str | None = Header(None)):
        account, _ = sync_identity(x_bekhi_sync, x_bekhi_device)
        await google_or_404(request).unlink(account)
        return {"ok": True}

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

    if settings.web_dir and (settings.web_dir / "index.html").is_file():
        app.mount("/", _AppFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("bekhi_api.main:app", host="0.0.0.0", port=8000, reload=False)
