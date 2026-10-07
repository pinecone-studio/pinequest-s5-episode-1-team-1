"""Duudlaga STT (https://duudlaga.dev/developers) — Mongolian and Mongolian/English speech."""

from __future__ import annotations

import logging

import httpx

from .base import ProviderUserError

log = logging.getLogger(__name__)

# Duudlaga error code -> Mongolian message safe to show the user.
ERRORS_MN = {
    "insufficient_credits": "Duudlaga-ийн кредит дууссан байна. duudlaga.dev консолоос цэнэглэнэ үү.",
    "payment_required": "Duudlaga-ийн төлбөрийн асуудлаас болж түр зогссон байна. Консолоо шалгана уу.",
    "rate_limit_exceeded": "Хэт олон хүсэлт ирлээ. Түр хүлээгээд дахин оролдоно уу.",
    "daily_spend_cap_exceeded": "Duudlaga-ийн өдрийн хязгаарт хүрлээ.",
    "concurrency_limit_exceeded": "Хэт олон хүсэлт зэрэг ирлээ. Дахин оролдоно уу.",
}


class DuudlagaSpeechToText:
    def __init__(self, http: httpx.AsyncClient, api_key: str, base_url: str) -> None:
        self._http = http
        self._key = api_key
        self._url = base_url.rstrip("/") + "/v1/stt/transcriptions"

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        r = await self._http.post(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            files={"file": ("voice.wav", audio, mime_type)},
            timeout=30,
        )
        if r.status_code == 200:
            return str(r.json().get("text") or "").strip()
        code = _error_code(r)
        if code == "no_speech":
            return ""  # the API layer turns this into the standard "сайн сонсогдсонгүй" reply
        log.warning("duudlaga stt failed: http=%s code=%s", r.status_code, code)
        if r.status_code in (401, 403):
            raise ProviderUserError("Duudlaga API key буруу байна (apps/api/.env).", "stt_failed")
        if r.status_code == 402 and code not in ERRORS_MN:
            code = "insufficient_credits"  # 402 always means the prepaid balance cannot cover the request
        if code in ERRORS_MN:
            raise ProviderUserError(ERRORS_MN[code], "stt_failed")
        r.raise_for_status()
        raise RuntimeError(f"unexpected duudlaga response {r.status_code}")


def _error_code(r: httpx.Response) -> str | None:
    try:
        body = r.json()
    except ValueError:
        return None
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return err.get("code")
    if isinstance(err, str):
        return err  # {"error": "insufficient_credits", "message": "..."}
    return body.get("code") if isinstance(body, dict) else None
