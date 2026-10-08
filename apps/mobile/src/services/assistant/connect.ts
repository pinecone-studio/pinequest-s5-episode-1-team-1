import Constants from "expo-constants";
import { getIpAddressAsync, getNetworkStateAsync, NetworkStateType } from "expo-network";
import { Platform } from "react-native";
import type { AssistantClient } from "./AssistantClient";
import { HttpAssistantClient } from "./HttpAssistantClient";
import { PreviewAssistantClient } from "./PreviewAssistantClient";
import { loadServerAddress, saveServerAddress } from "./server-address";

const API_PORT = 8000;
const PROBE_TIMEOUT_MS = 3000;
const SCAN_TIMEOUT_MS = 800;
const SCAN_BATCH = 32;

let current: string | null = null;
let connecting: Promise<AssistantClient> | null = null;

/** The API in use: the address that last answered its health check, else the configured one. */
export function apiBaseUrl(): string {
  return current ?? configuredBaseUrl() ?? `http://localhost:${API_PORT}`;
}

/**
 * EXPO_PUBLIC_API_URL wins. Otherwise the same host that serves the app: the browser's
 * host on web, the dev machine's LAN address in Expo Go. An installed APK has neither.
 */
function configuredBaseUrl(): string | null {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (Platform.OS === "web" && typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  return host ? `http://${host}:${API_PORT}` : null;
}

/**
 * Live client if the backend answers its health check, otherwise the offline preview.
 * Tries the configured address, then the one that answered last time, then looks for the
 * PC on the phone's Wi-Fi (an installed app moves between networks; the PC's address changes).
 */
export function connectAssistant(): Promise<AssistantClient> {
  connecting ??= findApi()
    .then((base) => {
      if (!base) return new PreviewAssistantClient();
      current = base;
      saveServerAddress(base);
      return new HttpAssistantClient(base);
    })
    .finally(() => {
      connecting = null;
    });
  return connecting;
}

async function findApi(): Promise<string | null> {
  const known = [configuredBaseUrl(), loadServerAddress()].filter((b): b is string => b !== null);
  for (const base of new Set(known)) {
    if (await isBekhiApi(base, PROBE_TIMEOUT_MS)) return base;
  }
  return Platform.OS === "web" ? null : scanWifi();
}

/** Every other address of the phone's /24 network, a batch at a time; the first BEKHI API wins. */
async function scanWifi(): Promise<string | null> {
  try {
    const state = await getNetworkStateAsync();
    if (state.type !== NetworkStateType.WIFI && state.type !== NetworkStateType.ETHERNET) return null;
    const match = /^(\d+\.\d+\.\d+)\.(\d+)$/.exec(await getIpAddressAsync());
    const prefix = match?.[1];
    const own = Number(match?.[2]);
    if (!prefix) return null;
    const hosts = Array.from({ length: 254 }, (_, i) => i + 1).filter((h) => h !== own);
    for (let i = 0; i < hosts.length; i += SCAN_BATCH) {
      const batch = hosts.slice(i, i + SCAN_BATCH).map((h) => `http://${prefix}.${h}:${API_PORT}`);
      const answers = await Promise.all(batch.map(async (b) => ((await isBekhiApi(b, SCAN_TIMEOUT_MS)) ? b : null)));
      const found = answers.find((b) => b !== null);
      if (found) return found;
    }
  } catch {
    // no network information: stay offline
  }
  return null;
}

/** True when `base` answers like the BEKHI API, not just any server on that port. */
async function isBekhiApi(base: string, timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${base}/api/v1/health`, { signal: controller.signal });
    if (!res.ok) return false;
    const body = (await res.json()) as { status?: unknown; llm?: unknown; stt?: unknown } | null;
    return body?.status === "ok" && body.llm !== undefined && body.stt !== undefined;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
