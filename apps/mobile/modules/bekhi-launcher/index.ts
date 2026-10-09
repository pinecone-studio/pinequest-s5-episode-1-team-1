import { requireOptionalNativeModule } from "expo";

/** An app on the phone's home screen. */
export interface InstalledApp {
  /** The name under its icon. */
  label: string;
  packageName: string;
}

interface BekhiLauncherModule {
  listApps(): Promise<InstalledApp[]>;
  /** Opens the app as tapping its icon does; false when it is not installed. */
  openApp(packageName: string): Promise<boolean>;
}

/** Only in BEKHI's own Android build (android/ in this module); null in Expo Go, on the iPhone and the web. */
export const BekhiLauncher = requireOptionalNativeModule<BekhiLauncherModule>("BekhiLauncher");
