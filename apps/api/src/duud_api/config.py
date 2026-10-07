"""Settings from environment (apps/api/.env). Secrets never leave the server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

API_ROOT = Path(__file__).resolve().parents[2]  # apps/api
REPO_ROOT = API_ROOT.parents[1]

load_dotenv(API_ROOT / ".env")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    gender: str  # "эр" | "эм"
    paid: bool = False  # Voice Library voice: the API refuses it on a free ElevenLabs plan


# Checked with eleven_v4_turbo speaking Mongolian. Premade voices work on the free plan;
# the native Mongolian (Khalkha) voices are Voice Library voices and need a paid plan.
ELEVENLABS_VOICES = [
    Voice("pNInz6obpgDQGcFmaJgB", "Adam", "эр"),
    Voice("JBFqnCBsd6RMkjVDRZzb", "George", "эр"),
    Voice("nPczCjzI2devNBz1zQrb", "Brian", "эр"),
    Voice("onwK4e9ZLuTAKqWW03F9", "Daniel", "эр"),
    Voice("TX3LPaxmHKxFdv7VOQHJ", "Liam", "эр"),
    Voice("iP95p4xoKVk53GoZ742B", "Chris", "эр"),
    Voice("EXAVITQu4vr4xnSDxMaL", "Sarah", "эм"),
    Voice("XrExE9yKIg1WjnnlVkGX", "Matilda", "эм"),
    Voice("FGY2WhTYpPnrIDTdsKH5", "Laura", "эм"),
    Voice("cgSgspJ2msm6clMCkdW9", "Jessica", "эм"),
    Voice("pFZP5JQG7iQjIQuC4Bku", "Lily", "эм"),
    Voice("Xb7hH8MSUJpSbSDYk0k2", "Alice", "эм"),
    Voice("WgH4JH8sD6a2SIrujiKn", "Sarnai (Монгол)", "эм", paid=True),
    Voice("RbMF2tQ1nCK38TfvNGLk", "Ganbold (Монгол)", "эр", paid=True),
]


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    gemini_stt_model: str
    gemini_stt_live_model: str | None
    gemini_tts_models: list[str]
    gemini_tts_voice: str
    gemini_fallback_models: list[str]
    stt_provider: str
    stt_fallback_provider: str | None
    llm_provider: str
    tts_provider: str
    tts_fallback_provider: str | None
    duudlaga_api_key: str | None
    duudlaga_api_url: str
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    contracts_dir: Path
    open_meteo_base_url: str
    open_meteo_geocoding_url: str
    max_audio_bytes: int
    rate_limit_per_minute: int
    desktop_actions: bool
    web_search_provider: str | None
    tavily_api_key: str | None
    log_level: str
    cors_origins: list[str] = field(default_factory=list)

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        # flash-lite: ~1.5 s per turn and correct on the intent fixtures; full Flash took ~6-13 s.
        gemini_model=os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite",
        # Hearing Mongolian numbers needs a full Flash model; flash-lite misheard "есөн цагт" in tests.
        gemini_stt_model=os.getenv("GEMINI_STT_MODEL") or "gemini-3.6-flash",
        # Dedicated transcription model (Live API), tried before GEMINI_STT_MODEL. Set it empty to disable.
        gemini_stt_live_model=os.getenv("GEMINI_STT_LIVE_MODEL", "gemini-3.5-transcribe-live") or None,
        # Free tier allows few TTS requests per day per model; the next model is tried on 429.
        gemini_tts_models=_csv(os.getenv("GEMINI_TTS_MODELS")) or ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"],
        gemini_tts_voice=os.getenv("GEMINI_TTS_VOICE") or "Kore",
        gemini_fallback_models=_csv(os.getenv("GEMINI_FALLBACK_MODELS")) or ["gemini-flash-lite-latest", "gemini-3.8-flash"],
        stt_provider=os.getenv("STT_PROVIDER") or "gemini",
        stt_fallback_provider=os.getenv("STT_FALLBACK_PROVIDER") or None,
        llm_provider=os.getenv("LLM_PROVIDER") or "gemini",
        tts_provider=os.getenv("TTS_PROVIDER") or "elevenlabs",
        # Speaks when the main TTS fails (bad key, no credits). Set it empty to disable.
        tts_fallback_provider=os.getenv("TTS_FALLBACK_PROVIDER", "gemini") or None,
        duudlaga_api_key=os.getenv("DUUDLAGA_API_KEY") or None,
        duudlaga_api_url=os.getenv("DUUDLAGA_API_URL") or "https://api.duudlaga.dev",
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
        # "Ganbold" — Khalkha Mongolian male voice from the ElevenLabs Voice Library.
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID") or "RbMF2tQ1nCK38TfvNGLk",
        # Only the eleven_v4 family speaks Mongolian (v3, multilingual_v2 and flash reject "mn").
        # eleven_v4 pronounced the test sentences exactly; eleven_v4_turbo is faster (~1.2 s vs ~1.9 s).
        elevenlabs_model_id=os.getenv("ELEVENLABS_MODEL_ID") or "eleven_v4",
        contracts_dir=Path(os.getenv("CONTRACTS_DIR") or REPO_ROOT / "packages" / "contracts"),
        open_meteo_base_url=os.getenv("OPEN_METEO_BASE_URL") or "https://api.open-meteo.com",
        open_meteo_geocoding_url=os.getenv("OPEN_METEO_GEOCODING_URL") or "https://geocoding-api.open-meteo.com",
        # 30 s of 16 kHz mono 16-bit PCM is ~0.96 MB (AUDIO_UPLOAD in contracts); allow headroom.
        max_audio_bytes=int(os.getenv("MAX_AUDIO_BYTES") or 1_500_000),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE") or 30),
        # Windows: the web app on this PC can set reminders/alarms/notes here (desktop.py). Local requests only.
        desktop_actions=(os.getenv("DESKTOP_ACTIONS") or "true").lower() in ("1", "true", "yes"),
        # tavily: 1,000 free searches a month (TAVILY_API_KEY). gemini: Google Search grounding, which
        # needs billing on the Gemini key (the free tier answers 429).
        web_search_provider=os.getenv("WEB_SEARCH_PROVIDER", "tavily") or None,
        tavily_api_key=os.getenv("TAVILY_API_KEY") or None,
        log_level=os.getenv("LOG_LEVEL") or "INFO",
        cors_origins=_csv(os.getenv("CORS_ORIGINS")) or ["http://localhost:8081"],
    )
