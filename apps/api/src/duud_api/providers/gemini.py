"""Gemini implementations of SpeechToText, TextToSpeech and LLMPlanner (google-genai SDK)."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
import wave
from typing import Any

from google.genai import errors, types

from .base import FunctionCall, FunctionSpec, HistoryMessage, SearchError

# Measured on Mongolian test clips: a strict verbatim instruction halved the character error rate.
# The old prompt listed assistant topics, and the model "heard" commands that were never spoken
# ("Өнөөдөр бороо орох уу?" -> "Утсаар ярьж орхи").
STT_INSTRUCTION = (
    "Transcribe the audio verbatim. The speaker is talking to a voice assistant in Mongolian (Khalkha), "
    "sometimes mixing in English words. Write Mongolian in Cyrillic and keep English words in Latin script "
    "(Wi-Fi, Bluetooth). Write exactly what was said: do not translate, answer, summarise, correct or add "
    "words that were not spoken. Write clock times and numbers as digits: 'есөн цагт' -> '9 цагт', "
    "'долоон цаг гучинд' -> '7:30-д'. Output only the transcript. If there is no speech, output nothing."
)

log = logging.getLogger(__name__)

# Transient capacity errors: try the next model instead of failing the user.
RETRYABLE = {429, 500, 503, 504}
# A model that ran out of quota (429) is tried last for a while, so each request
# does not pay for a round trip that is certain to fail.
QUOTA_COOLDOWN_SECONDS = 120
_quota_exhausted_until: dict[str, float] = {}

LIVE_TIMEOUT_SECONDS = 10
LIVE_CHUNK_BYTES = 32_000  # 1 s of 16 kHz 16-bit mono


def thinking_for(model: str) -> types.ThinkingConfig:
    """Lite models support MINIMAL thinking (fastest); full Flash models need at least LOW."""
    level = types.ThinkingLevel.MINIMAL if "lite" in model else types.ThinkingLevel.LOW
    return types.ThinkingConfig(thinking_level=level)


def _by_availability(models: list[str]) -> list[str]:
    now = time.monotonic()
    return sorted(models, key=lambda m: _quota_exhausted_until.get(m, 0) > now)  # stable: keeps the given order


async def generate_with_fallback(
    client: Any, models: list[str], *, contents: Any, config: types.GenerateContentConfig, thinking: bool = True
) -> Any:
    resp, _ = await _generate(client, models, contents=contents, config=config, thinking=thinking)
    return resp


async def _generate(
    client: Any, models: list[str], *, contents: Any, config: types.GenerateContentConfig, thinking: bool = True
) -> tuple[Any, str]:
    """The response and the model that produced it."""
    last: Exception | None = None
    for model in _by_availability(models):
        try:
            resp = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config.model_copy(update={"thinking_config": thinking_for(model)}) if thinking else config,
            )
            return resp, model
        except (errors.ServerError, errors.ClientError) as e:
            code = getattr(e, "code", None)
            if code not in RETRYABLE:
                raise
            if code == 429:
                _quota_exhausted_until[model] = time.monotonic() + QUOTA_COOLDOWN_SECONDS
            log.warning("gemini model %s unavailable (%s), trying next", model, code)
            last = e
    assert last is not None
    raise last


def _pcm16_mono(wav_bytes: bytes) -> tuple[bytes, int] | None:
    """Raw PCM and sample rate of a 16-bit mono WAV, or None for anything else."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                return None
            return w.readframes(w.getnframes()), w.getframerate()
    except (wave.Error, EOFError):
        return None


def _wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class GeminiSpeechToText:
    """Mongolian STT. Uses Gemini's dedicated transcription model (Live API) when configured:
    on the test clips it was close to error-free, where prompted generateContent models
    misheard roughly half of them. Falls back to prompted transcription if it fails."""

    def __init__(self, client: Any, models: list[str], live_model: str | None = None) -> None:
        self._client = client
        self._models = models
        self._live_model = live_model

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        pcm = _pcm16_mono(audio) if self._live_model else None
        if pcm is not None:
            try:
                return await self._transcribe_live(*pcm)
            except Exception as e:
                log.warning("gemini live stt failed (%s); using %s", type(e).__name__, self._models[0])
        resp = await generate_with_fallback(
            self._client,
            self._models,
            contents=[types.Part.from_bytes(data=audio, mime_type=mime_type)],
            config=types.GenerateContentConfig(system_instruction=STT_INSTRUCTION, temperature=0),
        )
        return (resp.text or "").strip()

    async def _transcribe_live(self, pcm: bytes, rate: int) -> str:
        config = types.LiveConnectConfig(
            input_audio_transcription=types.AudioTranscriptionConfig(language_codes=["mn-MN"]),
            # The recording is already complete, so mark the utterance explicitly. Server-side voice
            # activity detection sometimes never saw the end of a clip and the session hung.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
        )
        parts: list[str] = []
        async with asyncio.timeout(LIVE_TIMEOUT_SECONDS):
            async with self._client.aio.live.connect(model=self._live_model, config=config) as session:
                await session.send_realtime_input(activity_start=types.ActivityStart())
                for i in range(0, len(pcm), LIVE_CHUNK_BYTES):
                    await session.send_realtime_input(
                        audio=types.Blob(data=pcm[i : i + LIVE_CHUNK_BYTES], mime_type=f"audio/pcm;rate={rate}")
                    )
                await session.send_realtime_input(activity_end=types.ActivityEnd())
                async for msg in session.receive():
                    content = msg.server_content
                    if content is None:
                        continue
                    if content.input_transcription and content.input_transcription.text:
                        parts.append(content.input_transcription.text.strip())
                    if content.generation_complete or content.turn_complete:
                        break
        return " ".join(p for p in parts if p)


class GeminiTextToSpeech:
    """Fallback Mongolian TTS. Returns 16-bit mono WAV."""

    def __init__(self, client: Any, models: list[str], voice: str) -> None:
        self._client = client
        self._models = models
        self._voice = voice

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        # ElevenLabs voice ids mean nothing here: the fallback always uses its own voice.
        resp = await generate_with_fallback(
            self._client,
            self._models,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    language_code="mn-MN",
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._voice)
                    ),
                ),
            ),
            thinking=False,
        )
        blob = resp.candidates[0].content.parts[0].inline_data
        if blob is None or not blob.data:
            raise RuntimeError("gemini tts returned no audio")
        mime = (blob.mime_type or "").lower()
        if mime.startswith(("audio/wav", "audio/x-wav")):
            return blob.data
        # Raw PCM ("audio/L16;codec=pcm;rate=24000"): add a WAV header so players can open it.
        rate = re.search(r"rate=(\d+)", mime)
        return _wav(blob.data, int(rate.group(1)) if rate else 24000)


class GeminiWebSearch:
    """Web search through Gemini's Google Search grounding. It needs a key with grounding quota
    (a free-tier key gets 429), so a failure is reported as is: no retry on other models, and
    no quota cooldown that would also slow the planner down."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    async def search(self, query: str) -> dict[str, Any]:
        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "Search the web and answer with current facts, in Mongolian, in 2-4 plain sentences. "
                        "Say where the facts come from. If the results do not answer the question, say so."
                    ),
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
        except errors.ClientError as e:
            # 429 at once: the key has no Google Search quota (Gemini's free tier).
            raise SearchError("WEB_SEARCH_UNAVAILABLE" if e.code == 429 else "WEB_SEARCH_FAILED") from e
        meta = resp.candidates[0].grounding_metadata if resp.candidates else None
        chunks = (meta.grounding_chunks or []) if meta else []
        sources = [{"title": c.web.title, "url": c.web.uri} for c in chunks if c.web][:5]
        return {"answer": (resp.text or "").strip(), "sources": sources}


class GeminiPlanner:
    """Plans one turn with function calling. plan() starts it; follow_up() hands the results
    of the model's calls back so it can continue (the agent loop)."""

    def __init__(self, client: Any, models: list[str]) -> None:
        self._client = client
        self._models = models
        self._contents: list[types.Content] = []
        self._config: types.GenerateContentConfig | None = None
        self._last: types.Content | None = None

    async def plan(
        self,
        *,
        system: str,
        history: list[HistoryMessage],
        user_text: str,
        functions: list[FunctionSpec],
    ) -> list[FunctionCall]:
        self._contents = [
            types.Content(role="user" if m.role == "user" else "model", parts=[types.Part(text=m.text)])
            for m in history
        ]
        self._contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        self._config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(name=f.name, description=f.description, parameters_json_schema=f.parameters)
                        for f in functions
                    ]
                )
            ],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY)
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return await self._step()

    async def follow_up(self, results: list[tuple[FunctionCall, dict[str, Any]]]) -> list[FunctionCall]:
        if self._last is None:
            raise RuntimeError("follow_up() before plan()")
        # The model's turn goes back unchanged: Gemini 3 needs its thought signatures.
        self._contents.append(self._last)
        self._contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=call.name, response=result) for call, result in results],
            )
        )
        return await self._step()

    async def _step(self) -> list[FunctionCall]:
        resp, model = await _generate(self._client, self._models, contents=self._contents, config=self._config)
        # Thought signatures belong to the model that wrote them: stay on it for the follow-ups.
        self._models = [model, *(m for m in self._models if m != model)]
        self._last = resp.candidates[0].content if resp.candidates else types.Content(role="model", parts=[])
        return [FunctionCall(name=c.name or "", args=dict(c.args or {})) for c in (resp.function_calls or [])]

