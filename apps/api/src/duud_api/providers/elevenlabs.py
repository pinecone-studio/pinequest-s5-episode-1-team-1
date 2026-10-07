"""ElevenLabs TTS. Mongolian needs an eleven_v4 model (the API default, multilingual_v2, has no Mongolian)."""

from __future__ import annotations

import logging

import httpx

from .base import ProviderUserError, VoiceNeedsPaidPlan

log = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsTextToSpeech:
    def __init__(self, http: httpx.AsyncClient, api_key: str, voice_id: str, model_id: str) -> None:
        self._http = http
        self._key = api_key
        self._voice = voice_id
        self._model = model_id

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        voice_id = voice or self._voice
        body = {"text": text, "model_id": self._model, "language_code": "mn"}
        r = await self._post(voice_id, body)
        if r.status_code in (400, 422) and "language" in r.text.lower():
            # Some models reject language_code; Mongolian Cyrillic is still detected from the text.
            r = await self._post(voice_id, {k: v for k, v in body.items() if k != "language_code"})
        if r.status_code == 200:
            return r.content
        detail = r.text[:300]
        log.warning("elevenlabs tts failed: http=%s %s", r.status_code, detail)
        if "paid_plan_required" in detail and voice_id != self._voice:
            raise VoiceNeedsPaidPlan(voice_id)  # the chosen voice only; the default one still works
        if "paid_plan_required" in detail:
            # Voice Library voices (e.g. "Ganbold") need a paid plan over the API; premade voices do not.
            raise ProviderUserError(
                "ElevenLabs-ийн үнэгүй эрхээр Voice Library-ийн хоолойг API-аар ашиглах боломжгүй. "
                "Төлбөртэй багц авах эсвэл ELEVENLABS_VOICE_ID-д үндсэн (premade) хоолой тавина уу.",
                "tts_failed",
            )
        if "missing_permissions" in detail:
            # A restricted key: valid, but the "Text to Speech" access was not enabled for it.
            raise ProviderUserError(
                "ElevenLabs API key-д 'Text to Speech' эрх алга. elevenlabs.io → Developers → API Keys дээр "
                "key-ээ засаад Text to Speech-ийг асаана уу.",
                "tts_failed",
            )
        if r.status_code == 401 or "invalid_api_key" in detail:
            raise ProviderUserError(
                "ElevenLabs API key буруу байна (apps/api/.env). Key-г бүтнээр нь хуулж тавина уу.", "tts_failed"
            )
        if "voice_not_found" in detail or r.status_code == 404:
            raise ProviderUserError(
                "ElevenLabs-д энэ хоолой олдсонгүй. Voice Library-с 'Ganbold' хоолойг өөрийн бүртгэлд нэмнэ үү.",
                "tts_failed",
            )
        if "quota" in detail.lower() or r.status_code == 402:
            raise ProviderUserError("ElevenLabs-ийн эрх (кредит) дууссан байна.", "tts_failed")
        raise RuntimeError(f"elevenlabs http {r.status_code}")

    async def _post(self, voice_id: str, body: dict) -> httpx.Response:
        return await self._http.post(
            f"{BASE_URL}/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self._key, "accept": "audio/mpeg"},
            json=body,
            timeout=30,
        )
