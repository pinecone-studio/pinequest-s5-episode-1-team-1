"""In-memory conversation store (Phase 3). Supabase replaces it in Phase 8 behind the
same methods. Keeps only what the planner needs: recent turns and pending actions."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from .models import ActionRequest
from .providers.base import HistoryMessage

MAX_HISTORY = 12
MAX_CONVERSATIONS = 1000
TTL_SECONDS = 2 * 60 * 60


@dataclass
class PendingTurn:
    actions: list[ActionRequest]
    now_iso: str
    # Limitation messages to say after the outcome ("VS Code нээлээ" + what BEKHI could not do).
    notes: list[str] = field(default_factory=list)


@dataclass
class Conversation:
    history: deque[HistoryMessage] = field(default_factory=lambda: deque(maxlen=MAX_HISTORY))
    pending: dict[UUID, PendingTurn] = field(default_factory=dict)
    touched: float = field(default_factory=time.monotonic)


class MemoryStore:
    def __init__(self) -> None:
        self._conversations: dict[UUID, Conversation] = {}

    def get_or_create(self, conversation_id: UUID | None) -> tuple[UUID, Conversation]:
        self._evict()
        if conversation_id is not None and conversation_id in self._conversations:
            conv = self._conversations[conversation_id]
        else:
            conversation_id = conversation_id or uuid4()
            conv = self._conversations[conversation_id] = Conversation()
        conv.touched = time.monotonic()
        return conversation_id, conv

    def get(self, conversation_id: UUID) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def _evict(self) -> None:
        now = time.monotonic()
        for cid in [c for c, v in self._conversations.items() if now - v.touched > TTL_SECONDS]:
            del self._conversations[cid]
        while len(self._conversations) >= MAX_CONVERSATIONS:
            oldest = min(self._conversations, key=lambda c: self._conversations[c].touched)
            del self._conversations[oldest]
