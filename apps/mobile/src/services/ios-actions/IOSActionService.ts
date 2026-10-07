import type { ActionResult, ToolArguments } from "@duud/contracts";

/** What an action implementation reports. The dispatcher adds action_id and tool. */
export type ActionOutcome = Pick<ActionResult, "status" | "executed_via" | "error_code"> & {
  match_count?: number | null;
  /** What the action found, e.g. list_reminders' items; the backend words it. */
  data?: ActionResult["data"];
};

export interface NotificationRequest {
  title: string;
  body: string;
  fire_at: string;
}

/**
 * The only door from React Native to iPhone functionality. Screens and the store
 * never touch platform APIs directly. Implementations:
 * - LinkingIOSActionService: URL-scheme actions only (works in Expo Go)
 * - Native (Phase 9): Swift module over EventKit / Contacts / AlarmKit / MessageUI
 */
export interface IOSActionService {
  callContact(args: ToolArguments<"call_contact">): Promise<ActionOutcome>;
  sendMessage(args: ToolArguments<"send_message">): Promise<ActionOutcome>;
  createReminder(args: ToolArguments<"create_reminder">): Promise<ActionOutcome>;
  createCalendarEvent(args: ToolArguments<"create_calendar_event">): Promise<ActionOutcome>;
  createAlarm(args: ToolArguments<"create_alarm">): Promise<ActionOutcome>;
  createNote(args: ToolArguments<"create_note">): Promise<ActionOutcome>;
  createNotification(req: NotificationRequest): Promise<ActionOutcome>;
  openMaps(args: ToolArguments<"open_maps">): Promise<ActionOutcome>;
  openUrl(args: ToolArguments<"open_url">): Promise<ActionOutcome>;
  openApp(args: ToolArguments<"open_app">): Promise<ActionOutcome>;
  setTimer(args: ToolArguments<"set_timer">): Promise<ActionOutcome>;
  listReminders(args: ToolArguments<"list_reminders">): Promise<ActionOutcome>;
  cancelReminder(args: ToolArguments<"cancel_reminder">): Promise<ActionOutcome>;
  computerControl(args: ToolArguments<"computer_control">): Promise<ActionOutcome>;
  executeShortcut(name: string, input?: string): Promise<ActionOutcome>;
}

export const unsupported = (error_code: string): ActionOutcome => ({
  status: "unsupported",
  executed_via: null,
  error_code,
});
