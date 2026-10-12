import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import { RoutineKind } from "@bekhi/contracts";
import { toLocalIso } from "@/lib/time";
import type { ActionOutcome } from "./IOSActionService";
import type { ScheduledItem } from "./scheduled";

let handlerSet = false;

/**
 * Android plays a notification the way its channel says (and a channel cannot be changed
 * once created). Alarms and timers sound on the alarm stream, so the phone on vibrate
 * still rings.
 */
const ANDROID_CHANNELS: Record<"reminders" | "alarms", { id: string } & Notifications.NotificationChannelInput> = {
  reminders: { id: "bekhi-reminders", name: "Сануулга", importance: Notifications.AndroidImportance.HIGH },
  alarms: {
    id: "bekhi-alarms",
    name: "Сэрүүлэг, таймер",
    importance: Notifications.AndroidImportance.MAX,
    audioAttributes: { usage: Notifications.AndroidAudioUsage.ALARM },
  },
};
let channelsReady: Promise<unknown> | null = null;

function createAndroidChannels(): Promise<unknown> {
  channelsReady ??= Promise.all(
    Object.values(ANDROID_CHANNELS).map(({ id, ...channel }) =>
      Notifications.setNotificationChannelAsync(id, {
        sound: "default",
        vibrationPattern: [0, 400, 200, 400],
        lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
        ...channel,
      }),
    ),
  ).catch((e: unknown) => {
    channelsReady = null;
    throw e;
  });
  return channelsReady;
}

/**
 * Channel, permission and handler for a notification: the Android channel to post it on, or why
 * it cannot be scheduled.
 */
async function prepare(ringtone: boolean): Promise<{ channelId: string | undefined } | ActionOutcome> {
  let channelId: string | undefined;
  if (Platform.OS === "android") {
    // Before the permission request: Android 13+ shows its prompt only once a channel exists.
    try {
      await createAndroidChannels();
      channelId = (ringtone ? ANDROID_CHANNELS.alarms : ANDROID_CHANNELS.reminders).id;
    } catch {
      // the default channel still delivers it, just more quietly
    }
  }
  const permission = await Notifications.requestPermissionsAsync({
    ios: { allowAlert: true, allowSound: true, allowBadge: false },
  });
  if (!permission.granted) {
    return { status: "permission_denied", executed_via: "react_native", error_code: "NOTIFICATIONS_DENIED" };
  }
  if (!handlerSet) {
    // Also show and sound it when BEKHI is open at that moment.
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    handlerSet = true;
  }
  return { channelId };
}

/**
 * A local notification at `fireAtIso`: how Expo Go (no EventKit/AlarmKit) does reminders,
 * alarms, event reminders and timers. It is a notification, not a Clock alarm: in silent
 * mode it does not ring, and the reply says so.
 */
export async function scheduleNotification(
  fireAtIso: string,
  content: { title: string; body?: string; ringtone?: boolean; kind?: string; syncId?: string },
): Promise<ActionOutcome> {
  const date = new Date(fireAtIso);
  if (!(date.getTime() > Date.now())) {
    return { status: "failed", executed_via: "react_native", error_code: "TIME_IN_PAST" };
  }
  const ready = await prepare(content.ringtone ?? false);
  if ("status" in ready) return ready;
  const { channelId } = ready;
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: content.title,
        body: content.body ?? null,
        // On Android the channel decides the sound; "defaultRingtone" is an iOS name.
        sound: content.ringtone && Platform.OS === "ios" ? "defaultRingtone" : "default",
        // Read back by listScheduled(): what it is and when, as the user said it, and which
        // synced alarm it is a copy of (alarm-sync.ts).
        data: { bekhi: true, kind: content.kind ?? "reminder", fireAt: fireAtIso, syncId: content.syncId ?? null },
      },
      trigger: channelId
        ? { type: Notifications.SchedulableTriggerInputTypes.DATE, date, channelId }
        : { type: Notifications.SchedulableTriggerInputTypes.DATE, date },
    });
    return { status: "succeeded", executed_via: "react_native", error_code: null };
  } catch {
    return { status: "failed", executed_via: "react_native", error_code: "NOTIFICATION_FAILED" };
  }
}

const ROUTINES: Record<RoutineKind, { title: string; body: string }> = {
  daily_briefing: { title: "Өдрийн тойм", body: "Дарж сонсоорой: цаг агаар, өнөөдөр хийх зүйлс." },
};

/** "07:00" -> the next time it is that o'clock here, as local ISO. */
function nextAt(time: string): string {
  const [hour = 0, minute = 0] = time.split(":").map(Number);
  const next = new Date();
  next.setHours(hour, minute, 0, 0);
  if (next.getTime() <= Date.now()) next.setDate(next.getDate() + 1);
  return toLocalIso(next);
}

/**
 * A routine: a notification every day at `time` (local), replacing the routine's earlier time.
 * Tapping it opens BEKHI, which runs the routine (onRoutineOpened).
 */
export async function scheduleRoutine(time: string, routine: RoutineKind): Promise<ActionOutcome> {
  const ready = await prepare(false);
  if ("status" in ready) return ready;
  const [hour = 0, minute = 0] = time.split(":").map(Number);
  try {
    const earlier = (await Notifications.getAllScheduledNotificationsAsync()).filter(
      (n) => n.content.data?.bekhi === true && n.content.data.routine === routine,
    );
    await cancelScheduled(earlier.map((n) => n.identifier));
    await Notifications.scheduleNotificationAsync({
      content: { ...ROUTINES[routine], sound: "default", data: { bekhi: true, kind: "routine", routine, time } },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour, minute, channelId: ready.channelId },
    });
    return { status: "succeeded", executed_via: "react_native", error_code: null, data: { next_at: nextAt(time) } };
  } catch {
    return { status: "failed", executed_via: "react_native", error_code: "NOTIFICATION_FAILED" };
  }
}

/** A routine notification counts as tapped "now" for this long (an old one must not run again). */
const FRESH_TAP_MS = 10 * 60_000;
const handledTaps = new Set<string>();

/**
 * Calls `run` when the user taps a routine's notification: the tap that opened BEKHI, and any
 * tap while it runs. Returns the unsubscribe function.
 */
export function onRoutineOpened(run: (routine: RoutineKind) => void): () => void {
  const handle = (response: Notifications.NotificationResponse | null) => {
    const { request, date } = response?.notification ?? {};
    const data = request?.content.data;
    if (!request || data?.bekhi !== true || data.kind !== "routine") return;
    const key = `${request.identifier}@${date}`;
    if (handledTaps.has(key) || Date.now() - (date ?? 0) > FRESH_TAP_MS) return;
    handledTaps.add(key);
    Notifications.clearLastNotificationResponse();
    const routine = RoutineKind.safeParse(data.routine);
    if (routine.success) run(routine.data);
  };
  handle(Notifications.getLastNotificationResponse());
  const subscription = Notifications.addNotificationResponseReceivedListener(handle);
  return () => subscription.remove();
}

/** BEKHI's notifications still to come, soonest first (other apps' are left out). */
export async function listScheduled(): Promise<ScheduledItem[]> {
  const all = await Notifications.getAllScheduledNotificationsAsync();
  return all
    .flatMap((n) => {
      const data = n.content.data;
      if (data?.bekhi === true && data.kind === "routine" && typeof data.time === "string") {
        // Every day: listed at its next time, so it can be told and cancelled like a reminder.
        return [{ id: n.identifier, title: n.content.title ?? "", kind: "routine", fire_at: nextAt(data.time) }];
      }
      if (data?.bekhi !== true || typeof data.fireAt !== "string") return [];
      const syncId = typeof data.syncId === "string" ? data.syncId : undefined;
      return [
        { id: n.identifier, title: n.content.title ?? "", kind: String(data.kind ?? "reminder"), fire_at: data.fireAt, sync_id: syncId },
      ];
    })
    .sort((a, b) => Date.parse(a.fire_at) - Date.parse(b.fire_at));
}

export async function cancelScheduled(ids: string[]): Promise<void> {
  await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id)));
}
