import { z } from "zod";
import { ActionRequest, ActionResult } from "./actions";
import {
  DEFAULT_TIMEZONE,
  IanaTimezone,
  IsoDateTime,
  SpokenText,
  TtsVoice,
  Uuid,
} from "./common";
import { isDeviceTool, TravelMode } from "./tools";

// ---------------------------------------------------------------------------
// Device capabilities — sent with every request so the backend can plan
// (e.g. explain the alarm limitation up front when AlarmKit is unavailable).
// ---------------------------------------------------------------------------

export const PermissionState = z.enum([
  "granted",
  "limited", // Contacts on iOS 18+: user shared only selected contacts
  "write_only", // Calendar on iOS 17+: can add events, cannot read
  "denied",
  "not_determined",
  "restricted",
  "unavailable",
]);
export type PermissionState = z.infer<typeof PermissionState>;

export const DeviceCapabilities = z.object({
  /** "web": the browser on the computer that runs the API. */
  platform: z.enum(["ios", "android", "web"]),
  os_version: z.string().max(16),
  app_version: z.string().max(32),
  permissions: z.object({
    microphone: PermissionState,
    contacts: PermissionState,
    calendar: PermissionState,
    reminders: PermissionState,
    notifications: PermissionState,
    alarms: PermissionState,
  }),
  features: z.object({
    /** AlarmKit present (iOS 26+). */
    alarmkit: z.boolean(),
    app_intents: z.boolean(),
    /** shortcuts:// URL scheme can be opened. */
    shortcuts: z.boolean(),
    /** MFMessageComposeViewController.canSendText() */
    message_compose: z.boolean(),
    google_maps_installed: z.boolean(),
  }),
});
export type DeviceCapabilities = z.infer<typeof DeviceCapabilities>;

/** Sent alongside audio (multipart "context" field) or text. */
export const AssistantContext = z.object({
  conversation_id: Uuid.nullable(),
  /** Device clock at request time; the backend resolves "маргааш" etc. against this. */
  client_now: IsoDateTime,
  timezone: IanaTimezone.default(DEFAULT_TIMEZONE),
  /** Response language. Mongolian unless the user explicitly asks to switch. */
  response_language: z.string().min(2).max(8).default("mn"),
  tts_voice: TtsVoice.default("female"),
  device: DeviceCapabilities,
});
export type AssistantContext = z.infer<typeof AssistantContext>;

export const ChatRequest = z.object({
  text: z.string().min(1).max(2000),
  context: AssistantContext,
});
export type ChatRequest = z.infer<typeof ChatRequest>;

// ---------------------------------------------------------------------------
// Assistant turn
// ---------------------------------------------------------------------------

/**
 * - final:                   nothing left to do; `response` is the final answer
 * - awaiting_confirmation:   at least one action needs the user's yes/no first
 * - awaiting_device:         device actions must run, then POST /assistant/actions/results
 * - awaiting_clarification:  backend needs more info before it can plan any action
 */
export const TurnStage = z.enum([
  "final",
  "awaiting_confirmation",
  "awaiting_device",
  "awaiting_clarification",
]);
export type TurnStage = z.infer<typeof TurnStage>;

export const Clarification = z.object({
  question: SpokenText,
  options: z.array(z.string().max(100)).max(10),
});
export type Clarification = z.infer<typeof Clarification>;

/** Something the user asked for that iOS does not allow an app to do. */
export const LimitationCode = z.enum([
  "system_settings_toggle", // Wi-Fi, Bluetooth, airplane mode, brightness...
  "alarm_api_unavailable", // < iOS 26, no AlarmKit
  "apple_notes_no_api",
  "silent_call_or_message", // placing calls / sending messages without user interaction
  "third_party_app_control", // controlling other apps without a public integration
  "background_listening", // always-on wake word
  "other",
]);
export type LimitationCode = z.infer<typeof LimitationCode>;

export const Limitation = z.object({
  code: LimitationCode,
  message: SpokenText,
  /** Closest supported alternative, e.g. a Shortcut the user can create. */
  alternative: z
    .object({
      kind: z.enum(["shortcut", "open_settings", "in_app", "none"]),
      description: SpokenText,
    })
    .nullable(),
});
export type Limitation = z.infer<typeof Limitation>;

const AssistantTurnBase = z.object({
  conversation_id: Uuid,
  turn_id: Uuid,
  /** STT output (voice) or the submitted text (chat). */
  transcript: z.string().max(2000),
  /**
   * What the user asked, restated by the assistant in one short sentence. Speech
   * recognition can mishear words; this shows how BEKHI understood the request.
   */
  summary: z.string().max(300).nullable().optional(),
  /** Primary intent: a tool name, "multi", "chitchat", "clarification" or "unsupported". */
  intent: z.string().max(64),
  stage: TurnStage,
  /**
   * Text to show/speak NOW. When device actions are pending this is a confirmation
   * prompt or empty — it must never claim an action that has not run yet.
   */
  response: SpokenText,
  actions: z.array(ActionRequest).max(5),
  requires_confirmation: z.boolean(),
  requires_clarification: z.boolean(),
  clarification: Clarification.nullable(),
  limitations: z.array(Limitation),
  audio_url: z.url().nullable(),
});

export const AssistantTurn = AssistantTurnBase.superRefine((turn, ctx) => {
  const pendingDevice = turn.actions.some(
    (a) => isDeviceTool(a.tool) && a.result === null,
  );
  const needsConfirm = turn.actions.some((a) => a.confirmation.required);

  if (turn.requires_confirmation !== needsConfirm) {
    ctx.addIssue({
      code: "custom",
      message:
        "requires_confirmation must match actions[].confirmation.required",
    });
  }
  if (turn.requires_clarification !== (turn.clarification !== null)) {
    ctx.addIssue({
      code: "custom",
      message: "requires_clarification must match clarification presence",
    });
  }
  if (turn.stage === "final" && pendingDevice) {
    ctx.addIssue({
      code: "custom",
      message: "a final turn cannot contain unexecuted device actions",
    });
  }
  if (turn.stage === "awaiting_confirmation" && !needsConfirm) {
    ctx.addIssue({
      code: "custom",
      message: "awaiting_confirmation requires an action needing confirmation",
    });
  }
  if (turn.stage === "awaiting_device" && (!pendingDevice || needsConfirm)) {
    ctx.addIssue({
      code: "custom",
      message:
        "awaiting_device requires pending device actions and no confirmation",
    });
  }
  if (turn.stage === "awaiting_clarification" && turn.clarification === null) {
    ctx.addIssue({
      code: "custom",
      message: "awaiting_clarification requires a clarification",
    });
  }
  for (const a of turn.actions) {
    if (!isDeviceTool(a.tool) && a.result === null) {
      ctx.addIssue({
        code: "custom",
        message: `backend tool ${a.tool} must include its result`,
      });
    }
    if (a.confirmation.required && !a.confirmation.prompt) {
      ctx.addIssue({
        code: "custom",
        message: `action ${a.id} requires a confirmation prompt`,
      });
    }
  }
});
export type AssistantTurn = z.infer<typeof AssistantTurn>;

// ---------------------------------------------------------------------------
// POST /api/v1/assistant/actions/results — device reports what actually happened
// ---------------------------------------------------------------------------

export const ActionResultsRequest = z.object({
  conversation_id: Uuid,
  turn_id: Uuid,
  results: z.array(ActionResult).min(1).max(5),
});
export type ActionResultsRequest = z.infer<typeof ActionResultsRequest>;

export const ActionResultsResponse = z.object({
  conversation_id: Uuid,
  turn_id: Uuid,
  /** Final Mongolian answer composed from the real outcomes, e.g. partial-failure wording. */
  response: SpokenText,
  audio_url: z.url().nullable(),
});
export type ActionResultsResponse = z.infer<typeof ActionResultsResponse>;

// ---------------------------------------------------------------------------
// POST /api/v1/maps/directions — a route from where the phone is (Google Routes API)
// ---------------------------------------------------------------------------

export const LatLng = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});
export type LatLng = z.infer<typeof LatLng>;

export const DirectionsRequest = z.object({
  origin: LatLng,
  /** Free text, as the user said it: "Сансар", "Улсын их дэлгүүр". */
  destination: z.string().min(1).max(200),
  mode: TravelMode.default("driving"),
});
export type DirectionsRequest = z.infer<typeof DirectionsRequest>;

export const TransitVehicle = z.enum([
  "bus",
  "trolleybus",
  "tram",
  "train",
  "other",
]);
export type TransitVehicle = z.infer<typeof TransitVehicle>;

const HexColor = z.string().regex(/^#[0-9a-fA-F]{6}$/);

export const TransitStop = z.object({
  name: z.string().max(200),
  location: LatLng.nullable(),
});
export type TransitStop = z.infer<typeof TransitStop>;

/** The ride part of a transit step: which line to take, where to get on and off. */
export const TransitDetails = z.object({
  vehicle: TransitVehicle,
  /** As riders know the line: "М 3", "Ч:52". The full line name when there is no short one. */
  line: z.string().min(1).max(100),
  /** Operator's line colors, "#RRGGBB". */
  color: HexColor.nullable(),
  text_color: HexColor.nullable(),
  /** Where the line is heading, as shown on the vehicle. */
  headsign: z.string().max(200).nullable(),
  departure_stop: TransitStop,
  arrival_stop: TransitStop,
  /** Stops ridden, the one where the rider gets off included. */
  stop_count: z.number().int().min(0),
  /** Scheduled departure from `departure_stop` (Google's timetable, not live tracking). */
  departure_time: IsoDateTime.nullable(),
});
export type TransitDetails = z.infer<typeof TransitDetails>;

export const DirectionsStep = z.object({
  /** Turn instruction from Google, in Mongolian where Google has it. */
  instruction: z.string().max(500),
  distance_m: z.number().int().min(0),
  /** Time this step takes without traffic; for a ride, the time on board. */
  duration_s: z.number().int().min(0).default(0),
  /** Set on the steps ridden on public transport (mode "transit"). */
  transit: TransitDetails.nullable().optional(),
});
export type DirectionsStep = z.infer<typeof DirectionsStep>;

export const DirectionsResponse = z.object({
  distance_m: z.number().int().min(0),
  duration_s: z.number().int().min(0),
  destination: LatLng,
  /** The route to draw, origin first. */
  path: z.array(LatLng).max(5000),
  steps: z.array(DirectionsStep).max(200),
});
export type DirectionsResponse = z.infer<typeof DirectionsResponse>;

// ---------------------------------------------------------------------------
// POST /api/v1/maps/stops/nearby — bus stops around the phone (Google Places API)
// ---------------------------------------------------------------------------

export const NearbyStopsRequest = z.object({
  origin: LatLng,
  radius_m: z.number().int().min(100).max(2000).default(600),
});
export type NearbyStopsRequest = z.infer<typeof NearbyStopsRequest>;

export const NearbyStop = z.object({
  /** Google place id. */
  id: z.string().min(1).max(300),
  name: z.string().max(200),
  location: LatLng,
  /** Straight-line distance from `origin`. */
  distance_m: z.number().int().min(0),
});
export type NearbyStop = z.infer<typeof NearbyStop>;

export const NearbyStopsResponse = z.object({
  /** Nearest first. Both sides of a street are separate stops with the same name. */
  stops: z.array(NearbyStop).max(20),
});
export type NearbyStopsResponse = z.infer<typeof NearbyStopsResponse>;

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export const ApiErrorCode = z.enum([
  "stt_failed",
  "llm_failed",
  "tts_failed",
  "maps_failed",
  "invalid_request",
  "unauthorized",
  "rate_limited",
  "internal",
]);

export const ApiError = z.object({
  error: z.object({
    code: ApiErrorCode,
    /** Mongolian message safe to show the user. */
    message: SpokenText,
    request_id: z.string().max(64).nullable(),
  }),
});
export type ApiError = z.infer<typeof ApiError>;
