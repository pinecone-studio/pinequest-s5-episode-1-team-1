import { z } from "zod";
import { IanaTimezone, IsoDate, IsoDateTime } from "./common";

export const TOOL_NAMES = [
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
  "add_todo",
  "list_todos",
  "complete_todo",
  "delete_todo",
] as const;

export const ToolName = z.enum(TOOL_NAMES);
export type ToolName = z.infer<typeof ToolName>;

/**
 * Where an action runs. The backend decides WHAT should happen; the mobile app
 * decides HOW, walking a tool's `strategy` list in order and using the first
 * mechanism the device actually supports.
 */
export const ExecutionTarget = z.enum([
  "backend",
  "react_native",
  "native_swift",
  "app_intent",
  "shortcut",
  "url_scheme",
]);
export type ExecutionTarget = z.infer<typeof ExecutionTarget>;

/**
 * - never:        execute immediately
 * - if_ambiguous: execute immediately unless the request has missing/unclear fields
 * - always:       the user must explicitly confirm before execution
 */
export const ConfirmationPolicy = z.enum(["never", "if_ambiguous", "always"]);
export type ConfirmationPolicy = z.infer<typeof ConfirmationPolicy>;

export const DevicePermission = z.enum([
  "microphone",
  "contacts",
  "calendar_write",
  "reminders",
  "notifications",
  "alarms",
  "location",
]);
export type DevicePermission = z.infer<typeof DevicePermission>;

// ---------------------------------------------------------------------------
// Tool argument schemas. Names/values are normalized by the backend:
// contact names in nominative case ("Ээж рүүгээ" -> "Ээж"), times absolute.
// ---------------------------------------------------------------------------

const ContactName = z
  .string()
  .min(1)
  .max(100)
  .describe("Contact name as the user said it, normalized to nominative case, e.g. 'Ээж', 'Бат'");

export const CallContactArgs = z.object({
  contact_name: ContactName,
});

export const SendMessageArgs = z.object({
  contact_name: ContactName,
  body: z.string().min(1).max(1000),
});

export const CreateReminderArgs = z.object({
  title: z.string().min(1).max(200),
  due_at: IsoDateTime,
  timezone: IanaTimezone,
  notes: z.string().max(1000).optional(),
});

export const CreateCalendarEventArgs = z.object({
  title: z.string().min(1).max(200),
  start_at: IsoDateTime,
  /** Omitted => device uses DEFAULT_EVENT_DURATION_MINUTES. */
  end_at: IsoDateTime.optional(),
  all_day: z.boolean().default(false),
  timezone: IanaTimezone,
  location: z.string().max(200).optional(),
  notes: z.string().max(1000).optional(),
});

export const DEFAULT_EVENT_DURATION_MINUTES = 60;

export const CreateAlarmArgs = z.object({
  fire_at: IsoDateTime,
  timezone: IanaTimezone,
  label: z.string().max(100).optional(),
});

export const GetWeatherArgs = z.object({
  /** Free-text place, e.g. "Улаанбаатар". Omitted => user's current/default city. */
  location_name: z.string().max(100).optional(),
  date: IsoDate.optional(),
});

export const OpenMapsArgs = z.object({
  destination: z.string().min(1).max(200),
  mode: z.enum(["driving", "walking", "transit"]).default("driving"),
});

export const CreateNoteArgs = z.object({
  title: z.string().max(200).optional(),
  body: z.string().min(1).max(5000),
});

export const WebSearchArgs = z.object({
  query: z.string().min(1).max(300),
});

export const GetCurrentTimeArgs = z.object({
  timezone: IanaTimezone.optional(),
});

export const OpenUrlArgs = z.object({
  url: z.url({ protocol: /^https?$/ }).max(2000),
  /** What the page is, for the spoken reply ("YouTube", "Pinecone Academy-ийн сайт"). */
  title: z.string().max(100).optional(),
});

export const OpenAppArgs = z.object({
  /** The app as the user named it, e.g. "VS Code", "Chrome", "Spotify". */
  app_name: z.string().min(1).max(100),
});

export const SetTimerArgs = z.object({
  /** "10 минут" -> 600. The device adds it to its own clock, so no time maths in the model. */
  duration_seconds: z.number().int().min(1).max(86_400),
  label: z.string().max(100).optional(),
});

export const ListRemindersArgs = z.object({});

export const CancelReminderArgs = z.object({
  /** Words from the reminder's title, e.g. "ус уух". */
  query: z.string().max(100).optional(),
  /** Its time, when the user names it ("3 цагийнхаа"). */
  at: IsoDateTime.optional(),
  /** "Бүгдийг нь цуцал". */
  all: z.boolean().default(false),
});

export const AddTodoArgs = z.object({
  title: z.string().min(1).max(200),
  /** Optional deadline; a to-do needs no time. Does not ring: use create_reminder for that. */
  due_at: IsoDateTime.optional(),
});

export const TodoFilter = z.enum(["open", "today", "tomorrow", "week", "overdue", "done", "all"]);
export type TodoFilter = z.infer<typeof TodoFilter>;

export const ListTodosArgs = z.object({
  filter: TodoFilter.default("open"),
});

export const CompleteTodoArgs = z.object({
  /** Words from the to-do's title, e.g. "сүү". */
  query: z.string().min(1).max(100),
});

export const DeleteTodoArgs = z.object({
  query: z.string().max(100).optional(),
  /** "Бүгдийг нь устга". */
  all: z.boolean().default(false),
});

export const ComputerFolder = z.enum(["downloads", "documents", "desktop", "pictures", "music", "videos"]);
export type ComputerFolder = z.infer<typeof ComputerFolder>;

export const ComputerControlArgs = z.object({
  action: z.enum(["volume_up", "volume_down", "set_volume", "mute", "unmute", "lock_screen", "open_folder"]),
  /** set_volume: 0-100. */
  level: z.number().int().min(0).max(100).optional(),
  /** open_folder. */
  folder: ComputerFolder.optional(),
});

export const TOOL_ARGUMENT_SCHEMAS = {
  call_contact: CallContactArgs,
  create_reminder: CreateReminderArgs,
  create_calendar_event: CreateCalendarEventArgs,
  create_alarm: CreateAlarmArgs,
  get_weather: GetWeatherArgs,
  open_maps: OpenMapsArgs,
  create_note: CreateNoteArgs,
  send_message: SendMessageArgs,
  web_search: WebSearchArgs,
  get_current_time: GetCurrentTimeArgs,
  open_url: OpenUrlArgs,
  open_app: OpenAppArgs,
  set_timer: SetTimerArgs,
  list_reminders: ListRemindersArgs,
  cancel_reminder: CancelReminderArgs,
  computer_control: ComputerControlArgs,
  add_todo: AddTodoArgs,
  list_todos: ListTodosArgs,
  complete_todo: CompleteTodoArgs,
  delete_todo: DeleteTodoArgs,
} as const satisfies Record<ToolName, z.ZodType>;

export type ToolArguments<T extends ToolName> = z.output<(typeof TOOL_ARGUMENT_SCHEMAS)[T]>;

// ---------------------------------------------------------------------------
// Tool manifest: platform metadata shared by backend registry and mobile app.
// ---------------------------------------------------------------------------

export interface ToolManifestEntry {
  /** Who runs it. Backend tools return results inline; device tools come back as action requests. */
  executor: "backend" | "device";
  /** Ordered preference. The mobile app uses the first one that is available on this device. */
  strategy: readonly ExecutionTarget[];
  confirmation: ConfirmationPolicy;
  permissions: readonly DevicePermission[];
  /** Minimum iOS version for the primary strategy (strategy[0]). */
  min_ios: string;
  /** App Intent exposed to the Shortcuts app, or null if this tool is not exposed. */
  app_intent: string | null;
  /** Honest description of how it executes and what iOS does NOT allow. */
  notes: string;
}

export const MIN_IOS = "17.0";

export const TOOL_MANIFEST = {
  call_contact: {
    executor: "device",
    strategy: ["native_swift", "url_scheme"],
    confirmation: "always",
    permissions: ["contacts"],
    min_ios: MIN_IOS,
    app_intent: "BekhiCallContactIntent",
    notes:
      "Contact resolved on-device with the Contacts framework (supports iOS 18 limited access). " +
      "Call started via tel: URL; iOS shows its own call prompt. Apps cannot place cellular calls " +
      "silently, and CallKit only applies to an app's own VoIP calls. Outcome is 'handed_off'.",
  },
  send_message: {
    executor: "device",
    strategy: ["native_swift"],
    confirmation: "always",
    permissions: ["contacts"],
    min_ios: MIN_IOS,
    app_intent: null,
    notes:
      "MFMessageComposeViewController pre-fills recipient and body; the user must tap Send. " +
      "Apps cannot send SMS/iMessage silently. Compose result (sent/cancelled/failed) is reported.",
  },
  create_reminder: {
    executor: "device",
    strategy: ["native_swift"],
    confirmation: "if_ambiguous",
    permissions: ["reminders"],
    min_ios: MIN_IOS,
    app_intent: "BekhiCreateReminderIntent",
    notes: "EventKit EKReminder with an EKAlarm at due_at, saved to the default Reminders list.",
  },
  create_calendar_event: {
    executor: "device",
    strategy: ["native_swift"],
    confirmation: "if_ambiguous",
    permissions: ["calendar_write"],
    min_ios: MIN_IOS,
    app_intent: "BekhiCreateCalendarEventIntent",
    notes: "EventKit EKEvent using write-only calendar access (iOS 17+); BEKHI never reads the calendar.",
  },
  create_alarm: {
    executor: "device",
    strategy: ["native_swift", "shortcut"],
    confirmation: "if_ambiguous",
    permissions: ["alarms"],
    min_ios: "26.0",
    app_intent: null,
    notes:
      "iOS 26+: AlarmKit schedules a real alarm owned by BEKHI (not an entry in the Clock app's list). " +
      "Below iOS 26 there is no API to create alarms; BEKHI can run a user-installed Shortcut that uses " +
      "the Clock 'Create Alarm' action, or explain the limitation. A local notification is NOT an alarm " +
      "and is only offered explicitly, never substituted silently.",
  },
  open_maps: {
    executor: "device",
    strategy: ["url_scheme"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: "BekhiOpenMapsIntent",
    notes: "Apple Maps directions URL (maps.apple.com); Google Maps URL scheme if installed and preferred.",
  },
  create_note: {
    executor: "device",
    strategy: ["react_native", "shortcut"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes:
      "Apple Notes has no public API. Default: note stored inside BEKHI. Optional: user-installed " +
      "Shortcut using the Notes 'Create Note' action.",
  },
  get_weather: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: "BekhiGetWeatherIntent",
    notes: "Open-Meteo geocoding + forecast, executed by FastAPI.",
  },
  web_search: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Web search provider called by FastAPI; results summarized in Mongolian.",
  },
  get_current_time: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Computed from client_now + timezone sent with the request.",
  },
  open_url: {
    executor: "device",
    strategy: ["url_scheme"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "http(s) only, opened in the browser (the phone's browser, a new tab on the computer). Outcome is 'handed_off'.",
  },
  open_app: {
    executor: "device",
    strategy: ["react_native"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes:
      "Computer only: the web app asks the API running on the same Windows PC to launch a Start menu app " +
      "whose name matches. " +
      "iOS lets an app open other apps only through their URL schemes, so the iPhone reports unsupported; " +
      "Android in Expo Go does too (it needs a native build).",
  },
  set_timer: {
    executor: "device",
    strategy: ["react_native"],
    confirmation: "never",
    permissions: ["notifications"],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Rings after duration_seconds: a local notification on the phone, a looping toast on the computer.",
  },
  list_reminders: {
    executor: "device",
    strategy: ["react_native"],
    confirmation: "never",
    permissions: ["notifications"],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Reminders, alarms and timers BEKHI has scheduled on this device; returned in the result's data.",
  },
  cancel_reminder: {
    executor: "device",
    strategy: ["react_native"],
    confirmation: "never",
    permissions: ["notifications"],
    min_ios: MIN_IOS,
    app_intent: null,
    notes:
      "Cancels BEKHI's scheduled items matching the title words or time, or all of them. Several matches " +
      "without a filter ask which one (needs_clarification).",
  },
  computer_control: {
    executor: "device",
    strategy: ["react_native"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes:
      "Computer only (volume, mute, lock screen, open a standard folder), run by the API on the user's Windows " +
      "PC. iOS does not let apps change the volume or lock the phone, so the iPhone reports unsupported; " +
      "so does Android in Expo Go.",
  },
  add_todo: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "To-do list kept by FastAPI (a local file), the same on every device. No due time needed; it does not ring.",
  },
  list_todos: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Open, due-today, tomorrow, this-week, overdue or done to-dos, returned inline.",
  },
  complete_todo: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Marks the to-do matching the title words as done.",
  },
  delete_todo: {
    executor: "backend",
    strategy: ["backend"],
    confirmation: "never",
    permissions: [],
    min_ios: MIN_IOS,
    app_intent: null,
    notes: "Deletes the to-do matching the title words, or all of them.",
  },
} as const satisfies Record<ToolName, ToolManifestEntry>;

export function isDeviceTool(tool: ToolName): boolean {
  return TOOL_MANIFEST[tool].executor === "device";
}
