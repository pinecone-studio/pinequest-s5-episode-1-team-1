import * as IntentLauncher from "expo-intent-launcher";
import { Linking } from "react-native";
import type { ToolArguments } from "@bekhi/contracts";
import { BekhiLauncher } from "../../../modules/bekhi-launcher";
import { type AppTarget, type CatalogApp, fillQuery, findCatalogApp, rankApps } from "./app-catalog";
import { type ActionOutcome, unsupported } from "./IOSActionService";

type Phone = "ios" | "android";
type Via = ActionOutcome["executed_via"];

/** An Android screen that has not failed to start within this long has opened. */
const LAUNCH_SETTLE_MS = 700;

/**
 * Opens the app the user named on a phone: a search inside it when they asked for one and it has
 * a search link, else the app itself or its website, else (Android) any installed app with that
 * name. The outcome's data says which app opened and whether it searched, for the reply.
 */
export async function openAppOnPhone(args: ToolArguments<"open_app">, phone: Phone): Promise<ActionOutcome> {
  const app = findCatalogApp(args.app_name);
  if (app) {
    const done = (args.query ? await searchIn(app, args.query, phone) : null) ?? (await openFirst(app.open, phone));
    if (done) return opened(app.name, done.via, done.searched);
  }
  if (phone === "android" && BekhiLauncher) {
    try {
      const said = app ? [args.app_name, app.name, ...(app.aliases ?? [])] : [args.app_name];
      const [best] = rankApps(await BekhiLauncher.listApps(), said);
      if (!best) return { status: "failed", executed_via: "react_native", error_code: "APP_NOT_INSTALLED" };
      if (await BekhiLauncher.openApp(best.packageName)) return opened(best.label, "react_native", false);
    } catch (e) {
      console.warn("app launch failed", e);
    }
    return { status: "failed", executed_via: "react_native", error_code: "APP_OPEN_FAILED" };
  }
  return unsupported(phone === "ios" ? "IOS_CANNOT_OPEN_APPS" : "ANDROID_CANNOT_OPEN_APPS");
}

async function searchIn(app: CatalogApp, query: string, phone: Phone) {
  const links = (app.search ?? []).map((t) => (typeof t === "string" ? fillQuery(t, query) : { ios: fillQuery(t.ios, query) }));
  const done = await openFirst(links, phone);
  return done && { ...done, searched: true };
}

async function openFirst(targets: readonly AppTarget[], phone: Phone): Promise<{ via: Via; searched: boolean } | null> {
  for (const target of targets) {
    const via = await tryTarget(target, phone);
    if (via) return { via, searched: false };
  }
  return null;
}

function opened(app: string, via: Via, searched: boolean): ActionOutcome {
  // The other app has the screen now; what the user does there is not observable.
  return { status: "handed_off", executed_via: via, error_code: null, data: { app, searched } };
}

/** How the target opened, or null when this phone cannot open it. */
async function tryTarget(target: AppTarget, phone: Phone): Promise<Via | null> {
  if (typeof target === "string") return (await openLink(target)) ? "url_scheme" : null;
  if ("ios" in target) return phone === "ios" && (await openLink(target.ios)) ? "url_scheme" : null;
  if (phone !== "android") return null;
  if ("android" in target) return (await openPackage(target.android)) ? "react_native" : null;
  return (await openScreen(target.intent, target.category)) ? "react_native" : null;
}

async function openLink(url: string): Promise<boolean> {
  try {
    await Linking.openURL(url); // rejects when no installed app takes the link
    return true;
  } catch {
    return false;
  }
}

async function openPackage(packageName: string): Promise<boolean> {
  try {
    if (BekhiLauncher) return await BekhiLauncher.openApp(packageName);
    // Expo Go: Android 11+ may hide the app from it, and then this throws.
    IntentLauncher.openApplication(packageName);
    return true;
  } catch {
    return false;
  }
}

/** A system screen (camera, settings). Its promise settles only when the user comes back to BEKHI. */
async function openScreen(action: string, category?: string): Promise<boolean> {
  const launch = IntentLauncher.startActivityAsync(action, category ? { category } : undefined).then(
    () => true,
    () => false,
  );
  const settled = new Promise<boolean>((resolve) => setTimeout(() => resolve(true), LAUNCH_SETTLE_MS));
  return Promise.race([launch, settled]);
}
