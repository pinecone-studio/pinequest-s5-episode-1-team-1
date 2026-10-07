import * as Haptics from "expo-haptics";
import { Platform } from "react-native";

/** Haptics are a nicety: no-op on web, and never let a haptic failure surface as an error. */
export function tap() {
  if (Platform.OS === "web") return;
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
}

export function notify(kind: "success" | "warning") {
  if (Platform.OS === "web") return;
  const type = kind === "success" ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning;
  Haptics.notificationAsync(type).catch(() => {});
}
