import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import type { ActionOutcome } from "./IOSActionService";
import type { ScheduledItem } from "./scheduled";

let handlerSet = false;

/**
 * Android plays a notification the way its channel says (and a channel cannot be changed
 * once created). Alarms and timers sound on the alarm stream, so the phone on vibrate
 * still rings.
 */
const ANDROID_CHANNELS: Record<"reminders" | "alarms", { id: string } & Notifications.NotificationChannelInput> = {
  reminders: { id: "duud-reminders", name: "Сануулга", importance: Notifications.AndroidImportance.HIGH },
  alarms: {
    id: "duud-alarms",
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
 * A local notification at `fireAtIso`: how Expo Go (no EventKit/AlarmKit) does reminders,
 * alarms, event reminders and timers. It is a notification, not a Clock alarm: in silent
 * mode it does not ring, and the reply says so.
 */
export async function scheduleNotification(
  fireAtIso: string,
  content: { title: string; body?: string; ringtone?: boolean; kind?: string },
): Promise<ActionOutcome> {
  const date = new Date(fireAtIso);
  if (!(date.getTime() > Date.now())) {
    return { status: "failed", executed_via: "react_native", error_code: "TIME_IN_PAST" };
  }
  let channelId: string | undefined;
  if (Platform.OS === "android") {
    // Before the permission request: Android 13+ shows its prompt only once a channel exists.
    try {
      await createAndroidChannels();
      channelId = (content.ringtone ? ANDROID_CHANNELS.alarms : ANDROID_CHANNELS.reminders).id;
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
    // Also show and sound it when Duud is open at that moment.
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
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: content.title,
        body: content.body ?? null,
        // On Android the channel decides the sound; "defaultRingtone" is an iOS name.
        sound: content.ringtone && Platform.OS === "ios" ? "defaultRingtone" : "default",
        // Read back by listScheduled(): what it is and when, as the user said it.
        data: { duud: true, kind: content.kind ?? "reminder", fireAt: fireAtIso },
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

/** Duud's notifications still to come, soonest first (other apps' are left out). */
export async function listScheduled(): Promise<ScheduledItem[]> {
  const all = await Notifications.getAllScheduledNotificationsAsync();
  return all
    .flatMap((n) => {
      const data = n.content.data;
      if (data?.duud !== true || typeof data.fireAt !== "string") return [];
      return [{ id: n.identifier, title: n.content.title ?? "", kind: String(data.kind ?? "reminder"), fire_at: data.fireAt }];
    })
    .sort((a, b) => Date.parse(a.fire_at) - Date.parse(b.fire_at));
}

export async function cancelScheduled(ids: string[]): Promise<void> {
  await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id)));
}
