import { ExpoIOSActionService } from "./ExpoIOSActionService";
import { unsupported } from "./IOSActionService";

/**
 * An Android phone in Expo Go: the same calls (Contacts + tel:), messages (the SMS app),
 * reminders, alarms and timers as local notifications, and directions on BEKHI's own map
 * as on the iPhone. Opening other apps and changing the volume need a native build of BEKHI.
 */
export class ExpoAndroidActionService extends ExpoIOSActionService {
  openApp = async () => unsupported("ANDROID_CANNOT_OPEN_APPS");

  computerControl = async () => unsupported("ANDROID_NO_SYSTEM_CONTROL");
}
