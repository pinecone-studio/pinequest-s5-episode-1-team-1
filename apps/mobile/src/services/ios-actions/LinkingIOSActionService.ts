import { Linking } from "react-native";
import type { ToolArguments } from "@duud/contracts";
import { type ActionOutcome, type IOSActionService, unsupported } from "./IOSActionService";

/**
 * Implements only what plain URL schemes can do. Everything that needs EventKit,
 * Contacts, AlarmKit or MessageUI reports `unsupported` until the Swift module
 * exists (Phase 9) — it never pretends.
 */
export class LinkingIOSActionService implements IOSActionService {
  constructor(protected readonly nativeUnavailableCode: string) {}

  callContact: IOSActionService["callContact"] = async () => unsupported(this.nativeUnavailableCode);
  sendMessage: IOSActionService["sendMessage"] = async () => unsupported(this.nativeUnavailableCode);
  createReminder: IOSActionService["createReminder"] = async () => unsupported(this.nativeUnavailableCode);
  createCalendarEvent: IOSActionService["createCalendarEvent"] = async () => unsupported(this.nativeUnavailableCode);
  createAlarm: IOSActionService["createAlarm"] = async () => unsupported(this.nativeUnavailableCode);
  createNote: IOSActionService["createNote"] = async () => unsupported(this.nativeUnavailableCode);
  createNotification: IOSActionService["createNotification"] = async () => unsupported(this.nativeUnavailableCode);

  openMaps = async (args: ToolArguments<"open_maps">): Promise<ActionOutcome> => {
    const dirflg = { driving: "d", walking: "w", transit: "r" }[args.mode];
    const url = `https://maps.apple.com/?daddr=${encodeURIComponent(args.destination)}&dirflg=${dirflg}`;
    return openUrl(url);
  };

  openUrl = async (args: ToolArguments<"open_url">): Promise<ActionOutcome> => {
    if (!/^https?:\/\//i.test(args.url)) return { status: "failed", executed_via: null, error_code: "URL_NOT_HTTP" };
    return openUrl(args.url);
  };

  openApp: IOSActionService["openApp"] = async () => unsupported(this.nativeUnavailableCode);
  setTimer: IOSActionService["setTimer"] = async () => unsupported(this.nativeUnavailableCode);
  listReminders: IOSActionService["listReminders"] = async () => unsupported(this.nativeUnavailableCode);
  cancelReminder: IOSActionService["cancelReminder"] = async () => unsupported(this.nativeUnavailableCode);
  computerControl: IOSActionService["computerControl"] = async () => unsupported(this.nativeUnavailableCode);

  executeShortcut = async (name: string, input?: string): Promise<ActionOutcome> => {
    let url = `shortcuts://run-shortcut?name=${encodeURIComponent(name)}`;
    if (input !== undefined) url += `&input=text&text=${encodeURIComponent(input)}`;
    return openUrl(url);
  };
}

async function openUrl(url: string): Promise<ActionOutcome> {
  try {
    await Linking.openURL(url);
    // iOS opened another app; whether the user finishes there is not observable.
    return { status: "handed_off", executed_via: "url_scheme", error_code: null };
  } catch {
    return { status: "failed", executed_via: "url_scheme", error_code: "URL_OPEN_FAILED" };
  }
}
