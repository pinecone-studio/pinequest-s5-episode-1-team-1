import type { RoutineKind } from "@bekhi/contracts";
import type { ActionOutcome } from "./IOSActionService";
import type { ScheduledItem } from "./scheduled";

// Web: reminders go through the PC (DesktopActionService), so expo-notifications is not loaded here.

export async function scheduleNotification(
  _fireAtIso: string,
  _content: { title: string; body?: string; ringtone?: boolean; kind?: string; syncId?: string },
): Promise<ActionOutcome> {
  return { status: "unsupported", executed_via: null, error_code: "WEB_NO_IPHONE_ACTIONS" };
}

export async function listScheduled(): Promise<ScheduledItem[]> {
  return [];
}

export async function cancelScheduled(_ids: string[]): Promise<void> {}

export async function scheduleRoutine(_time: string, _routine: RoutineKind): Promise<ActionOutcome> {
  return { status: "unsupported", executed_via: null, error_code: "WEB_NO_IPHONE_ACTIONS" };
}

export function onRoutineOpened(_run: (routine: RoutineKind) => void): () => void {
  return () => {};
}
