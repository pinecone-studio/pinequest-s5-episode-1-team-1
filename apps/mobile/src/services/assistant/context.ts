import Constants from "expo-constants";
import { isRunningInExpoGo } from "expo";
import { Platform } from "react-native";
import type { AssistantContext } from "@bekhi/contracts";
import { deviceTimezone, toLocalIso } from "@/lib/time";

/**
 * Context sent with every request. Permissions are reported as not_determined
 * until the native module can query them (Phase 9 / 19).
 */
export function buildContext(conversationId: string | null): AssistantContext {
  const native = !isRunningInExpoGo();
  return {
    conversation_id: conversationId,
    client_now: toLocalIso(new Date()),
    timezone: deviceTimezone(),
    response_language: "mn",
    tts_voice: "female",
    device: {
      platform: Platform.OS === "android" ? "android" : Platform.OS === "web" ? "web" : "ios",
      os_version: String(Platform.Version),
      app_version: Constants.expoConfig?.version ?? "0.0.0",
      permissions: {
        microphone: "not_determined",
        contacts: "not_determined",
        calendar: "not_determined",
        reminders: "not_determined",
        notifications: "not_determined",
        alarms: "not_determined",
      },
      features: {
        alarmkit: false,
        app_intents: native,
        shortcuts: true,
        message_compose: false,
        google_maps_installed: false,
      },
    },
  };
}
