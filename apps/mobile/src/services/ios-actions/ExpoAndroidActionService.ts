import type { ToolArguments } from "@bekhi/contracts";
import { openAppOnPhone } from "./apps";
import { ExpoIOSActionService } from "./ExpoIOSActionService";
import { unsupported } from "./IOSActionService";

/**
 * An Android phone: the same calls (Contacts + tel:), messages (the SMS app), reminders, alarms
 * and timers as local notifications, and directions on BEKHI's own map as on the iPhone. Apps open
 * by their links and system screens; BEKHI's own build also opens any installed app by its name.
 * Changing the volume needs a native module that does not exist yet.
 */
export class ExpoAndroidActionService extends ExpoIOSActionService {
  openApp = (args: ToolArguments<"open_app">) => openAppOnPhone(args, "android");

  computerControl = async () => unsupported("ANDROID_NO_SYSTEM_CONTROL");
}
