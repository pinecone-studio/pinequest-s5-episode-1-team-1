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
    "find_bus_stops",
    "suggest_food",
    "show_recipe",
    "find_restaurants",
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
    "add_todo",
    "list_todos",
    "complete_todo",
    "delete_todo",
    "daily_briefing",
    "create_routine",
    "remember",
    "forget",
    "set_profile",
    "type_text",
    "play_video",
    "find_files",
    "open_file",
    "read_file",
    "look_at_screen",
    "read_webpage",
    "check_email",
    "read_email",
    "draft_email",
    "send_email",
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


TravelMode = Literal["driving", "walking", "transit"]


class LatLng(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DirectionsRequest(BaseModel):
    origin: LatLng
    destination: str = Field(min_length=1, max_length=200)
    mode: TravelMode = "driving"


TransitVehicle = Literal["bus", "trolleybus", "tram", "train", "other"]
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class TransitStop(BaseModel):
    name: str = Field(max_length=200)
    location: LatLng | None = None


class TransitDetails(BaseModel):
    vehicle: TransitVehicle
    line: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    text_color: str | None = Field(default=None, pattern=HEX_COLOR)
    headsign: str | None = Field(default=None, max_length=200)
    departure_stop: TransitStop
    arrival_stop: TransitStop
    stop_count: int = Field(ge=0)
    departure_time: str | None = None


class DirectionsStep(BaseModel):
    instruction: str = Field(max_length=500)
    distance_m: int = Field(ge=0)
    duration_s: int = Field(default=0, ge=0)
    transit: TransitDetails | None = None


class DirectionsResponse(BaseModel):
    distance_m: int = Field(ge=0)
    duration_s: int = Field(ge=0)
    destination: LatLng
    path: list[LatLng] = Field(max_length=5000)
    steps: list[DirectionsStep] = Field(max_length=200)


class NearbyStopsRequest(BaseModel):
    origin: LatLng
    radius_m: int = Field(default=600, ge=100, le=2000)


class NearbyStop(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    name: str = Field(max_length=200)
    location: LatLng
    distance_m: int = Field(ge=0)


class NearbyStopsResponse(BaseModel):
    stops: list[NearbyStop] = Field(max_length=20)


class RestaurantsRequest(BaseModel):
    origin: LatLng
    query: str | None = Field(default=None, min_length=1, max_length=60)
    radius_m: int = Field(default=1500, ge=300, le=5000)


class Restaurant(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    name: str = Field(max_length=200)
    location: LatLng
    distance_m: int = Field(ge=0)
    address: str | None = Field(default=None, max_length=300)
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_count: int | None = Field(default=None, ge=0)
    open_now: bool | None = None
    kind: str | None = Field(default=None, max_length=100)


class RestaurantsResponse(BaseModel):
    restaurants: list[Restaurant] = Field(max_length=20)


ApiErrorCode = Literal[
    "stt_failed", "llm_failed", "tts_failed", "maps_failed", "invalid_request", "unauthorized", "rate_limited", "internal"
]


class ApiErrorBody(BaseModel):
    code: ApiErrorCode
    message: str
    request_id: str | None = None


class ApiError(BaseModel):
    error: ApiErrorBody


# Alarm/timer sync between linked devices (packages/contracts src/sync.ts).
SyncPlatform = Literal["ios", "android", "web"]


class SyncDeviceRequest(BaseModel):
    platform: SyncPlatform


class SyncAlarm(BaseModel):
    id: UUID
    kind: Literal["alarm", "timer"]
    title: str = Field(min_length=1, max_length=100)
    fire_at: datetime

    @field_validator("fire_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("fire_at must include a UTC offset")
        return v


class SyncPublishResponse(BaseModel):
    other_devices: list[SyncPlatform]


class SyncCancelRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=50)


class SyncPullResponse(BaseModel):
    active: list[SyncAlarm]
    cancelled: list[UUID]
