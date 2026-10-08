"""Swappable AI providers. The pipeline depends only on the protocols in base.py."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import TypeVar

import httpx

from ..config import get_settings
from .base import LLMPlanner, ProviderUserError, SpeechToText, TextToSpeech, VoiceNeedsPaidPlan, WebSearch

log = logging.getLogger(__name__)

__all__ = ["ProviderNotConfigured", "ProviderUserError", "get_llm", "get_search", "get_stt", "get_tts"]

T = TypeVar("T")

# A provider that failed for an account reason (no credits, bad key) is skipped for a while,
# so every request does not wait for a round trip that is certain to fail again.
ACCOUNT_ERROR_COOLDOWN_SECONDS = 600
_skip_until: dict[str, float] = {}


class ProviderNotConfigured(RuntimeError):
    """A provider is selected but its credentials are missing."""


@lru_cache
def _gemini_client():
    from google import genai

    key = get_settings().gemini_api_key
    if not key:
        raise ProviderNotConfigured("GEMINI_API_KEY is not set in apps/api/.env")
    return genai.Client(api_key=key)


async def _primary_then_secondary(
    names: tuple[str, str], primary: Callable[[], Awaitable[T]], secondary: Callable[[], Awaitable[T]]
) -> T:
    if _skip_until.get(names[0], 0) > time.monotonic():
        return await secondary()
    try:
        return await primary()
    except VoiceNeedsPaidPlan:
        raise  # the provider works; only the chosen voice does not (the API retries with the default)
    except Exception as e:
        if isinstance(e, ProviderUserError):
            _skip_until[names[0]] = time.monotonic() + ACCOUNT_ERROR_COOLDOWN_SECONDS
        log.warning("%s failed (%s); falling back to %s", names[0], type(e).__name__, names[1])
        return await secondary()


class FallbackSpeechToText:
    """Primary STT, and if it fails (no credits, outage, bad key) the secondary one."""

    def __init__(self, primary: SpeechToText, secondary: SpeechToText, names: tuple[str, str]) -> None:
        self._primary, self._secondary, self._names = primary, secondary, names

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        return await _primary_then_secondary(
            self._names,
            lambda: self._primary.transcribe(audio, mime_type),
            lambda: self._secondary.transcribe(audio, mime_type),
        )


class FallbackTextToSpeech:
    """Primary TTS, and if it fails the secondary one."""

    def __init__(self, primary: TextToSpeech, secondary: TextToSpeech, names: tuple[str, str]) -> None:
        self._primary, self._secondary, self._names = primary, secondary, names

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        return await _primary_then_secondary(
            self._names, lambda: self._primary.synthesize(text, voice), lambda: self._secondary.synthesize(text)
        )


def _with_fallback(primary_name: str, fallback_name: str | None, build: Callable[[str], T], wrap) -> T:
    """The primary provider, wrapped with the fallback if one is configured. If only the
    fallback has credentials, it is used alone."""
    if not fallback_name or fallback_name == primary_name:
        return build(primary_name)
    try:
        secondary = build(fallback_name)
    except ProviderNotConfigured:
        return build(primary_name)
    try:
        primary = build(primary_name)
    except ProviderNotConfigured:
        return secondary
    return wrap(primary, secondary, (primary_name, fallback_name))


def get_stt(http: httpx.AsyncClient) -> SpeechToText:
    s = get_settings()
    return _with_fallback(s.stt_provider, s.stt_fallback_provider, lambda name: _stt(name, http), FallbackSpeechToText)


def _stt(provider: str, http: httpx.AsyncClient) -> SpeechToText:
    s = get_settings()
    if provider == "duudlaga":
        from .duudlaga import DuudlagaSpeechToText

        if not s.duudlaga_api_key:
            raise ProviderNotConfigured("DUUDLAGA_API_KEY is not set in apps/api/.env")
        return DuudlagaSpeechToText(http, s.duudlaga_api_key, s.duudlaga_api_url)
    if provider == "gemini":
        from .gemini import GeminiSpeechToText

        return GeminiSpeechToText(
            _gemini_client(), [s.gemini_stt_model, *s.gemini_fallback_models], s.gemini_stt_live_model
        )
    # "buzzasr" lands with apps/speech (Phase 5).
    raise ProviderNotConfigured(f"STT provider '{provider}' is not available yet")


def get_llm() -> LLMPlanner:
    s = get_settings()
    if s.llm_provider == "gemini":
        from .gemini import GeminiPlanner

        return GeminiPlanner(_gemini_client(), [s.gemini_model, *s.gemini_fallback_models])
    raise ProviderNotConfigured(f"LLM provider '{s.llm_provider}' is not available")


def get_search(http: httpx.AsyncClient) -> WebSearch | None:
    """The web_search tool's provider, or None when none is configured (the tool says so)."""
    s = get_settings()
    if s.web_search_provider == "tavily" and s.tavily_api_key:
        from .tavily import TavilyWebSearch

        return TavilyWebSearch(http, s.tavily_api_key)
    if s.web_search_provider == "gemini" and s.gemini_api_key:
        from .gemini import GeminiWebSearch

        return GeminiWebSearch(_gemini_client(), s.gemini_model)
    return None


def get_tts(http: httpx.AsyncClient) -> TextToSpeech:
    s = get_settings()
    return _with_fallback(s.tts_provider, s.tts_fallback_provider, lambda name: _tts(name, http), FallbackTextToSpeech)


def _tts(provider: str, http: httpx.AsyncClient) -> TextToSpeech:
    s = get_settings()
    if provider == "elevenlabs":
        from .elevenlabs import ElevenLabsTextToSpeech

        if not s.elevenlabs_api_key:
            raise ProviderNotConfigured("ELEVENLABS_API_KEY is not set in apps/api/.env")
        return ElevenLabsTextToSpeech(http, s.elevenlabs_api_key, s.elevenlabs_voice_id, s.elevenlabs_model_id)
    if provider == "gemini":
        from .gemini import GeminiTextToSpeech

        return GeminiTextToSpeech(_gemini_client(), s.gemini_tts_models, s.gemini_tts_voice)
    # "oron_tts" lands with apps/speech.
    raise ProviderNotConfigured(f"TTS provider '{provider}' is not available yet")
