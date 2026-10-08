"""Pydantic mirror of packages/contracts (wire format). Contract-tested against
packages/contracts/generated/wire.schema.json and packages/contracts/examples."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ToolName = Literal[
    "call_contact",
    "create_reminder",
    "create_calendar_event",
    "create_alarm",
    "get_weather",
    "open_maps",
    "create_note",
    "send_message",
    "web_search",
    "get_current_time",
    "open_url",
    "open_app",
    "set_timer",
    "list_reminders",
    "cancel_reminder",
    "computer_control",
]
ExecutionTarget = Literal["backend", "react_native", "native_swift", "app_intent", "shortcut", "url_scheme"]
ActionStatus = Literal[
    "succeeded", "handed_off", "cancelled", "permission_denied", "unsupported", "needs_clarification", "failed"
]
PermissionState = Literal["granted", "limited", "write_only", "denied", "not_determined", "restricted", "unavailable"]
TurnStage = Literal["final", "awaiting_confirmation", "awaiting_device", "awaiting_clarification"]
LimitationCode = Literal[
    "system_settings_toggle",
    "alarm_api_unavailable",
    "apple_notes_no_api",
    "silent_call_or_message",
    "third_party_app_control",
    "background_listening",
    "other",
]


class Permissions(BaseModel):
    microphone: PermissionState
    contacts: PermissionState
    calendar: PermissionState
    reminders: PermissionState
    notifications: PermissionState
    alarms: PermissionState


class Features(BaseModel):
    alarmkit: bool
    app_intents: bool
    shortcuts: bool
    message_compose: bool
    google_maps_installed: bool


class DeviceCapabilities(BaseModel):
    platform: Literal["ios", "android", "web"]  # web: the browser on the computer running the API
    os_version: str = Field(max_length=16)
    app_version: str = Field(max_length=32)
    permissions: Permissions
    features: Features


class AssistantContext(BaseModel):
    conversation_id: UUID | None
    client_now: datetime
    timezone: str = Field(default="Asia/Ulaanbaatar", min_length=1, max_length=64)
    response_language: str = Field(default="mn", min_length=2, max_length=8)
    tts_voice: Literal["female", "male"] = "female"
    device: DeviceCapabilities

    @field_validator("client_now")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("client_now must include a UTC offset")
        return v


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    context: AssistantContext


class Confirmation(BaseModel):
    required: bool
    prompt: str | None = Field(default=None, max_length=1000)


class ActionResult(BaseModel):
    action_id: str = Field(min_length=1, max_length=64)
    tool: ToolName
    status: ActionStatus
    executed_via: ExecutionTarget | None
    error_code: str | None = Field(default=None, max_length=64)
    match_count: int | None = Field(default=None, ge=0)
    data: dict[str, Any] | None = None


class ActionRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    tool: ToolName
    arguments: dict[str, Any]
    confirmation: Confirmation
    result: ActionResult | None = None


class Clarification(BaseModel):
    question: str = Field(max_length=1000)
    options: list[str] = Field(default_factory=list, max_length=10)


class Alternative(BaseModel):
    kind: Literal["shortcut", "open_settings", "in_app", "none"]
    description: str = Field(max_length=1000)


class Limitation(BaseModel):
    code: LimitationCode
    message: str = Field(max_length=1000)
    alternative: Alternative | None = None


class AssistantTurn(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    transcript: str = Field(max_length=2000)
    summary: str | None = Field(default=None, max_length=300)
    intent: str = Field(max_length=64)
    stage: TurnStage
    response: str = Field(max_length=1000)
    actions: list[ActionRequest] = Field(max_length=5)
    requires_confirmation: bool
    requires_clarification: bool
    clarification: Clarification | None
    limitations: list[Limitation]
    audio_url: str | None = None


class ActionResultsRequest(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    results: list[ActionResult] = Field(min_length=1, max_length=5)


class ActionResultsResponse(BaseModel):
    conversation_id: UUID
    turn_id: UUID
    response: str = Field(max_length=1000)
    audio_url: str | None = None


ApiErrorCode = Literal["stt_failed", "llm_failed", "tts_failed", "invalid_request", "unauthorized", "rate_limited", "internal"]


class ApiErrorBody(BaseModel):
    code: ApiErrorCode
    message: str
    request_id: str | None = None


class ApiError(BaseModel):
    error: ApiErrorBody
