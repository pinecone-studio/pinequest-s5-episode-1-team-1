import { AppState, Platform } from "react-native";
import { SyncPublishResponse, SyncPullResponse, type SyncAlarm, type SyncPlatform } from "@bekhi/contracts";
import { toLocalIso } from "@/lib/time";
import { apiBaseUrl } from "@/services/assistant/connect";
import { cancelScheduled, listScheduled, scheduleNotification } from "@/services/ios-actions/notifications";
import { ensureIdentity, formatSyncCode, normalizeSyncCode, platform, setIdentity, syncHeaders } from "./identity";

/**
 * Alarms and timers on every device linked with the same sync code (apps/api sync.py).
 *
 * Every device starts with its own code; typing another device's code joins it. The phone
 * pulls the shared list while BEKHI is open and schedules its own local copy ahead of time,
 * so it rings even without network at that moment. In the browser on the Windows PC, the
 * API running there does the pulling and rings them as toasts, even with the browser closed.
 */

const PULL_EVERY_MS = 30_000;
const TIMEOUT_MS = 8_000;
/** An alarm ringing within seconds is not scheduled again: device clocks differ a little. */
const MIN_LEAD_MS = 5_000;

let running = false;
let inFlight: Promise<void> | null = null;
/** Synced alarms already scheduled here, so one that has rung is not scheduled again. */
const scheduled = new Set<string>();

/** This device's code, to type on the user's other devices. */
export function syncCode(): string {
  return formatSyncCode(ensureIdentity().code);
}

async function call(path: string, init: { method?: string; body?: unknown } = {}): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(apiBaseUrl() + path, {
      method: init.method ?? "GET",
      headers: {
        ...syncHeaders(),
        ...(init.body !== undefined ? { "content-type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`sync ${path} answered ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** Phone: "this device is linked". Web: link the PC's API itself, which rings the alarms. */
async function linkDevice(): Promise<void> {
  const id = ensureIdentity();
  if (Platform.OS !== "web") {
    await call("/api/v1/sync/devices", { method: "POST", body: { platform } });
    return;
  }
  const res = await fetch(`${apiBaseUrl()}/api/v1/desktop/sync`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code: id.code }),
  });
  if (!res.ok) return; // not the browser on the PC that runs the API: nothing rings here
  const body = (await res.json().catch(() => null)) as { device_id?: unknown } | null;
  // Publish as the PC, so the other devices' replies say "компьютер" once, not twice.
  if (typeof body?.device_id === "string" && body.device_id !== id.deviceId) {
    setIdentity({ ...id, deviceId: body.device_id });
  }
}

/** Phone: schedule what the other devices set, drop what any device cancelled. */
async function pullToDevice(): Promise<void> {
  const { active, cancelled } = SyncPullResponse.parse(await call("/api/v1/sync/alarms"));
  const local = await listScheduled();
  const here = new Set(local.flatMap((i) => (i.sync_id ? [i.sync_id] : [])));
  for (const a of active) {
    if (here.has(a.id) || scheduled.has(a.id) || Date.parse(a.fire_at) <= Date.now() + MIN_LEAD_MS) continue;
    const outcome = await scheduleNotification(toLocalIso(new Date(a.fire_at)), {
      title: a.title,
      body: a.kind === "timer" ? "Таймер дууслаа" : "БЭХИ сэрүүлэг",
      ringtone: true,
      kind: a.kind,
      syncId: a.id,
    });
    if (outcome.status === "succeeded") scheduled.add(a.id);
  }
  const gone = new Set(cancelled);
  const drop = local.filter((i) => i.sync_id && gone.has(i.sync_id)).map((i) => i.id);
  if (drop.length > 0) await cancelScheduled(drop);
}

/** Brings this device up to date with the shared list (one run at a time). */
export function refreshAlarms(): Promise<void> {
  inFlight ??= (Platform.OS === "web" ? linkDevice() : pullToDevice()).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** Publishes an alarm/timer this device has just scheduled; returns the other linked devices. */
export async function publishAlarm(alarm: SyncAlarm): Promise<SyncPlatform[]> {
  const { other_devices } = SyncPublishResponse.parse(await call("/api/v1/sync/alarms", { method: "POST", body: alarm }));
  return other_devices;
}

export async function cancelAlarms(ids: string[]): Promise<void> {
  await call("/api/v1/sync/alarms/cancel", { method: "POST", body: { ids } });
}

/** Joins the devices that use `input` (another device's code). False if it is not a valid code. */
export async function linkWithCode(input: string): Promise<boolean> {
  const code = normalizeSyncCode(input);
  if (!code) return false;
  setIdentity({ ...ensureIdentity(), code });
  scheduled.clear();
  await linkDevice();
  if (Platform.OS !== "web") await refreshAlarms();
  return true;
}

/** Once the API answers: link this device, then keep pulling while BEKHI is open. */
export function startAlarmSync(): void {
  if (running) return;
  running = true;
  const quiet = (e: unknown) => console.warn("alarm sync failed", e);
  linkDevice()
    .then(() => (Platform.OS === "web" ? undefined : refreshAlarms()))
    .catch(quiet);
  if (Platform.OS === "web") return; // the PC's API pulls on its own
  setInterval(() => {
    if (AppState.currentState === "active") refreshAlarms().catch(quiet);
  }, PULL_EVERY_MS);
  AppState.addEventListener("change", (state) => {
    if (state === "active") refreshAlarms().catch(quiet);
  });
}
