import type { ActionOutcome } from "./IOSActionService";
import type { ScheduledItem } from "./scheduled";

// Web: reminders go through the PC (DesktopActionService), so expo-notifications is not loaded here.

export async function scheduleNotification(
  _fireAtIso: string,
  _content: { title: string; body?: string; ringtone?: boolean; kind?: string },
): Promise<ActionOutcome> {
  return { status: "unsupported", executed_via: null, error_code: "WEB_NO_IPHONE_ACTIONS" };
}

export async function listScheduled(): Promise<ScheduledItem[]> {
  return [];
}

export async function cancelScheduled(_ids: string[]): Promise<void> {}
