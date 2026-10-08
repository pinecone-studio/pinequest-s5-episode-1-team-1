import { Linking } from "react-native";
import * as SMS from "expo-sms";
import type { ToolArguments } from "@bekhi/contracts";
import { toLocalIso } from "@/lib/time";
import { lookupPhone, type ContactLookup } from "./contacts";
import { type ActionOutcome, type NotificationRequest, unsupported } from "./IOSActionService";
import { LinkingIOSActionService } from "./LinkingIOSActionService";
import { openInAppMap } from "./maps";
import { cancelScheduled, listScheduled, scheduleNotification } from "./notifications";
import { pickScheduled } from "./scheduled";

/**
 * What a real iPhone can do in Expo Go, without the native module (Phase 9): calls
 * (Contacts + tel:), messages (Contacts + the system message sheet), reminders, alarms
 * and event reminders as local notifications, and directions on BEKHI's own map screen.
 * Notes still need the native module.
 */
export class ExpoIOSActionService extends LinkingIOSActionService {
  openMaps = (args: ToolArguments<"open_maps">) => openInAppMap(args);

  callContact = async (args: ToolArguments<"call_contact">): Promise<ActionOutcome> => {
    const contact = await lookupPhone(args.contact_name).catch(lookupFailed);
    if (contact?.kind !== "found") return notReachable(contact);
    try {
      // iOS shows its own "Call …?" prompt; whether the call happens is not observable.
      await Linking.openURL(`tel:${contact.number.replace(/[^\d+]/g, "")}`);
      return { status: "handed_off", executed_via: "url_scheme", error_code: null };
    } catch {
      return { status: "failed", executed_via: "url_scheme", error_code: "URL_OPEN_FAILED" };
    }
  };

  sendMessage = async (args: ToolArguments<"send_message">): Promise<ActionOutcome> => {
    if (!(await SMS.isAvailableAsync())) return unsupported("SMS_UNAVAILABLE");
    const contact = await lookupPhone(args.contact_name).catch(lookupFailed);
    if (contact?.kind !== "found") return notReachable(contact);
    try {
      // The system message sheet: the user taps Send, and iOS reports whether they did.
      const { result } = await SMS.sendSMSAsync([contact.number], args.body);
      if (result === "sent") return { status: "succeeded", executed_via: "react_native", error_code: null };
      if (result === "cancelled") return { status: "cancelled", executed_via: "react_native", error_code: null };
      return { status: "handed_off", executed_via: "react_native", error_code: null };
    } catch {
      return { status: "failed", executed_via: "react_native", error_code: "SMS_FAILED" };
    }
  };

  createReminder = (args: ToolArguments<"create_reminder">) =>
    scheduleNotification(args.due_at, { title: args.title, body: args.notes ?? "БЭХИ сануулга", kind: "reminder" });

  createAlarm = (args: ToolArguments<"create_alarm">) =>
    scheduleNotification(args.fire_at, {
      title: args.label ?? "Сэрэх цаг боллоо",
      body: "БЭХИ сэрүүлэг",
      ringtone: true,
      kind: "alarm",
      syncId: args.sync_id,
    });

  createCalendarEvent = (args: ToolArguments<"create_calendar_event">) =>
    scheduleNotification(args.start_at, { title: args.title, body: args.location ?? "БЭХИ: эхлэх цаг боллоо", kind: "event" });

  // fire_at comes from the backend's clock, so every linked device rings at the same moment.
  setTimer = (args: ToolArguments<"set_timer">) =>
    scheduleNotification(args.fire_at ?? toLocalIso(new Date(Date.now() + args.duration_seconds * 1000)), {
      title: args.label ?? "Таймер",
      body: "Таймер дууслаа",
      ringtone: true,
      kind: "timer",
      syncId: args.sync_id,
    });

  listReminders = async (): Promise<ActionOutcome> => {
    try {
      const items = (await listScheduled()).slice(0, 10);
      return { status: "succeeded", executed_via: "react_native", error_code: null, data: { items } };
    } catch {
      return { status: "failed", executed_via: "react_native", error_code: "NOTIFICATIONS_FAILED" };
    }
  };

  cancelReminder = async (args: ToolArguments<"cancel_reminder">): Promise<ActionOutcome> => {
    try {
      const { matches, ambiguous } = pickScheduled(await listScheduled(), args);
      if (ambiguous) {
        return {
          status: "needs_clarification",
          executed_via: "react_native",
          error_code: "REMINDER_AMBIGUOUS",
          match_count: matches.length,
        };
      }
      if (matches.length === 0) return { status: "failed", executed_via: "react_native", error_code: "REMINDER_NOT_FOUND" };
      await cancelScheduled(matches.map((m) => m.id));
      return {
        status: "succeeded",
        executed_via: "react_native",
        error_code: null,
        data: {
          cancelled: matches.map((m) => m.title),
          // Cancelled on the server too (alarm-sync.ts), so the other devices drop their copies.
          cancelled_sync_ids: matches.flatMap((m) => (m.sync_id ? [m.sync_id] : [])),
        },
      };
    } catch {
      return { status: "failed", executed_via: "react_native", error_code: "NOTIFICATIONS_FAILED" };
    }
  };

  // iOS does not let apps change the volume, lock the phone or open folders.
  computerControl = async () => unsupported("IOS_NO_SYSTEM_CONTROL");

  createNotification = (req: NotificationRequest) => scheduleNotification(req.fire_at, { title: req.title, body: req.body });

  // iOS lets an app open another app only through that app's own URL scheme.
  openApp = async () => unsupported("IOS_CANNOT_OPEN_APPS");
}

/** Why a contact lookup threw, for the dev server log; the user hears a short sentence instead. */
function lookupFailed(e: unknown): null {
  console.warn("contact lookup failed", e);
  return null;
}

function notReachable(contact: ContactLookup | null): ActionOutcome {
  switch (contact?.kind) {
    case "permission_denied":
      return { status: "permission_denied", executed_via: "react_native", error_code: "CONTACTS_DENIED" };
    case "ambiguous":
      return {
        status: "needs_clarification",
        executed_via: "react_native",
        error_code: "CONTACT_AMBIGUOUS",
        match_count: contact.count,
      };
    case "not_found":
      return { status: "failed", executed_via: "react_native", error_code: "CONTACT_NOT_FOUND" };
    case "no_number":
      return { status: "failed", executed_via: "react_native", error_code: "CONTACT_NO_PHONE" };
    default:
      return { status: "failed", executed_via: "react_native", error_code: "CONTACTS_FAILED" };
  }
}
