from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    text: str


class ProviderUserError(RuntimeError):
    """A provider failure with a Mongolian message that is safe to show the user."""

    def __init__(self, message_mn: str, code: str) -> None:
        super().__init__(message_mn)
        self.message_mn = message_mn
        self.code = code


class VoiceNeedsPaidPlan(ProviderUserError):
    """The chosen voice (a Voice Library voice) is not available on a free ElevenLabs plan."""

    def __init__(self, voice_id: str) -> None:
        super().__init__("Энэ хоолой ElevenLabs-ийн төлбөртэй багц шаарддаг.", "voice_needs_paid_plan")
        self.voice_id = voice_id


class TextToSpeech(Protocol):
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """MP3 or WAV audio; the API reads the format from the bytes. `voice` is a provider voice
        id from the configured list; None means the default voice."""
        ...


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes, mime_type: str) -> str: ...


class LLMPlanner(Protocol):
    async def plan(
        self,
        *,
        system: str,
        history: list[HistoryMessage],
        user_text: str,
        functions: list[FunctionSpec],
    ) -> list[FunctionCall]:
        """Return the function calls the model chose. Must call at least one."""
        ...

    async def follow_up(self, results: list[tuple[FunctionCall, dict[str, Any]]]) -> list[FunctionCall]:
        """Give the model a result for every one of its last calls; return its next calls."""
        ...


class SearchError(RuntimeError):
    """A web search that failed for a known reason; `code` becomes the web_search error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WebSearch(Protocol):
    async def search(self, query: str) -> dict[str, Any]:
        """{"answer": Mongolian text, "sources": [{"title": ..., "url": ...}]}"""
        ...
