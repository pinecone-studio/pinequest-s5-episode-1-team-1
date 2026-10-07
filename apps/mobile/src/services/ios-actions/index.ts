import { isRunningInExpoGo } from "expo";
import { Platform } from "react-native";
import type { ActionRequest, ActionResult } from "@duud/contracts";
import { NATIVE_UNAVAILABLE } from "./codes";
import { DesktopActionService } from "./DesktopActionService";
import { ExpoAndroidActionService } from "./ExpoAndroidActionService";
import { ExpoIOSActionService } from "./ExpoIOSActionService";
import type { IOSActionService } from "./IOSActionService";

export { NATIVE_UNAVAILABLE };

const nativeUnavailable = isRunningInExpoGo() ? NATIVE_UNAVAILABLE.expoGo : NATIVE_UNAVAILABLE.notBuilt;

// Phase 9 replaces the dev-build branch with the Swift-backed implementation.
export const iosActions: IOSActionService =
  Platform.OS === "web"
    ? new DesktopActionService(NATIVE_UNAVAILABLE.web)
    : Platform.OS === "android"
      ? new ExpoAndroidActionService(nativeUnavailable)
      : new ExpoIOSActionService(nativeUnavailable);

/** Runs one device action and wraps the outcome as a contract ActionResult. */
export async function executeDeviceAction(service: IOSActionService, action: ActionRequest): Promise<ActionResult> {
  const outcome = await dispatch(service, action);
  return { action_id: action.id, tool: action.tool, ...outcome };
}

function dispatch(service: IOSActionService, action: ActionRequest) {
  switch (action.tool) {
    case "call_contact":
      return service.callContact(action.arguments);
    case "send_message":
      return service.sendMessage(action.arguments);
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
    case "get_weather":
    case "web_search":
    case "get_current_time":
      return Promise.resolve({ status: "failed" as const, executed_via: null, error_code: "BACKEND_TOOL_ON_DEVICE" });
  }
}
