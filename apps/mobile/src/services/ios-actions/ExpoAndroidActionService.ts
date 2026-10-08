import type { ToolArguments } from "@bekhi/contracts";
import { ExpoIOSActionService } from "./ExpoIOSActionService";
import { unsupported } from "./IOSActionService";
import { googleMapsUrl } from "./maps";

/**
 * An Android phone in Expo Go: the same calls (Contacts + tel:), messages (the SMS app) and
 * reminders, alarms and timers as local notifications as on the iPhone, with directions in
 * Google Maps. Opening other apps and changing the volume need a native build of BEKHI.
 */
export class ExpoAndroidActionService extends ExpoIOSActionService {
  openMaps = (args: ToolArguments<"open_maps">) => this.openUrl({ url: googleMapsUrl(args) });

  openApp = async () => unsupported("ANDROID_CANNOT_OPEN_APPS");

  computerControl = async () => unsupported("ANDROID_NO_SYSTEM_CONTROL");
}
