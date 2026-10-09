import { isRunningInExpoGo } from "expo";
import { Platform } from "react-native";
import type { ActionRequest, ActionResult } from "@bekhi/contracts";
import { cancelAlarms, publishAlarm, refreshAlarms } from "@/services/sync/alarm-sync";
import { NATIVE_UNAVAILABLE } from "./codes";
import { DesktopActionService } from "./DesktopActionService";
import { ExpoAndroidActionService } from "./ExpoAndroidActionService";
import { ExpoIOSActionService } from "./ExpoIOSActionService";
import type { ActionOutcome, ChosenContact, IOSActionService } from "./IOSActionService";

export { NATIVE_UNAVAILABLE };
export type { ChosenContact };

const nativeUnavailable = isRunningInExpoGo() ? NATIVE_UNAVAILABLE.expoGo : NATIVE_UNAVAILABLE.notBuilt;

// Phase 9 replaces the dev-build branch with the Swift-backed implementation.
export const iosActions: IOSActionService =
  Platform.OS === "web"
    ? new DesktopActionService(NATIVE_UNAVAILABLE.web)
    : Platform.OS === "android"
      ? new ExpoAndroidActionService(nativeUnavailable)
      : new ExpoIOSActionService(nativeUnavailable);

/**
 * Runs one device action and wraps the outcome as a contract ActionResult.
 * `chosen`: for a call or message, the contact the user picked on screen.
 */
export async function executeDeviceAction(
  service: IOSActionService,
  action: ActionRequest,
  chosen?: ChosenContact,
): Promise<ActionResult> {
  if (action.tool === "list_reminders" || action.tool === "cancel_reminder") {
    // Alarms set on the user's other devices are listed and cancelled here too.
    await refreshAlarms().catch((e: unknown) => console.warn("alarm sync failed", e));
  }
  const outcome = await withSync(action, await dispatch(service, action, chosen));
  return { action_id: action.id, tool: action.tool, ...outcome };
}

/**
 * Alarms and timers for all devices (sync_id set by the backend) go to the user's other
 * devices once this one has scheduled its copy; cancelling cancels them everywhere. The
 * outcome's data says what happened, so the reply is honest about the other devices.
 */
async function withSync(action: ActionRequest, outcome: ActionOutcome): Promise<ActionOutcome> {
  if (outcome.status !== "succeeded") return outcome;
  if (action.tool === "create_alarm" || action.tool === "set_timer") {
    const args = action.arguments;
    const fireAt = args.fire_at;
    if (!args.sync_id || !fireAt) return outcome;
    const alarm = action.tool === "create_alarm"
      ? { id: args.sync_id, kind: "alarm" as const, title: args.label ?? "Сэрэх цаг боллоо", fire_at: fireAt }
      : { id: args.sync_id, kind: "timer" as const, title: args.label ?? "Таймер", fire_at: fireAt };
    try {
      const others = await publishAlarm(alarm);
      return { ...outcome, data: { ...outcome.data, sync: { status: "sent", other_devices: others } } };
    } catch (e) {
      console.warn("alarm publish failed", e);
      return { ...outcome, data: { ...outcome.data, sync: { status: "failed" } } };
    }
  }
  if (action.tool === "cancel_reminder") {
    const ids = outcome.data?.cancelled_sync_ids;
    if (!Array.isArray(ids) || ids.length === 0) return outcome;
    try {
      await cancelAlarms(ids.map(String));
      return { ...outcome, data: { ...outcome.data, sync: { status: "sent" } } };
    } catch (e) {
      console.warn("alarm cancel sync failed", e);
      return { ...outcome, data: { ...outcome.data, sync: { status: "failed" } } };
    }
  }
  return outcome;
}

function dispatch(service: IOSActionService, action: ActionRequest, chosen?: ChosenContact) {
  switch (action.tool) {
    case "call_contact":
      return service.callContact(action.arguments, chosen);
    case "send_message":
      return service.sendMessage(action.arguments, chosen);
    case "create_reminder":
      return service.createReminder(action.arguments);
    case "create_calendar_event":
      return service.createCalendarEvent(action.arguments);
    case "create_alarm":
      return service.createAlarm(action.arguments);
    case "create_note":
      return service.createNote(action.arguments);
    case "open_maps":
      return service.openMaps(action.arguments);
    case "open_url":
      return service.openUrl(action.arguments);
    case "open_app":
      return service.openApp(action.arguments);
    case "set_timer":
      return service.setTimer(action.arguments);
    case "list_reminders":
      return service.listReminders(action.arguments);
    case "cancel_reminder":
      return service.cancelReminder(action.arguments);
    case "computer_control":
      return service.computerControl(action.arguments);
    case "create_routine":
      return service.createRoutine(action.arguments);
    case "get_weather":
    case "web_search":
    case "get_current_time":
    case "add_todo":
    case "list_todos":
    case "complete_todo":
    case "delete_todo":
    case "daily_briefing":
    case "remember":
    case "forget":
      return Promise.resolve({ status: "failed" as const, executed_via: null, error_code: "BACKEND_TOOL_ON_DEVICE" });
  }
}
