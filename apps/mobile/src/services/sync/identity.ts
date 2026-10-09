import { Platform } from "react-native";
import {
  SYNC_CODE_ALPHABET,
  SYNC_CODE_HEADER,
  SYNC_CODE_LENGTH,
  SYNC_DEVICE_HEADER,
  type SyncPlatform,
} from "@bekhi/contracts";
import { loadSync, saveSync, type SavedSync } from "./sync-storage";

/**
 * Who this device is to the API: its sync code (the account, shared by every device linked with
 * it) and its own device id. Every device starts with its own code; typing another device's code
 * joins that account, with its alarms and to-do list.
 */

export const platform: SyncPlatform = Platform.OS === "android" ? "android" : Platform.OS === "web" ? "web" : "ios";

let identity: SavedSync | null = null;

function randomInts(count: number, below: number): number[] {
  const bytes = new Uint8Array(count);
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let i = 0; i < count; i++) bytes[i] = Math.floor(Math.random() * 256);
  return Array.from(bytes, (b) => b % below);
}

function newCode(): string {
  return randomInts(SYNC_CODE_LENGTH, SYNC_CODE_ALPHABET.length)
    .map((i) => SYNC_CODE_ALPHABET[i])
    .join("");
}

function newDeviceId(): string {
  const hex = randomInts(16, 16)
    .map((i) => i.toString(16))
    .join("");
  return `${platform}-${hex}`;
}

/** Same rules as the server: case, dashes and spaces ignored, O/I/L read as 0/1/1. */
export function normalizeSyncCode(input: string): string | null {
  const code = input
    .toUpperCase()
    .replace(/[\s-]/g, "")
    .replace(/O/g, "0")
    .replace(/[IL]/g, "1");
  return code.length === SYNC_CODE_LENGTH && [...code].every((c) => SYNC_CODE_ALPHABET.includes(c)) ? code : null;
}

/** "ABCDEFGHJKMN" -> "ABCD-EFGH-JKMN", easier to read out and type. */
export const formatSyncCode = (code: string) => code.match(/.{1,4}/g)?.join("-") ?? code;

export function ensureIdentity(): SavedSync {
  if (identity) return identity;
  const saved = loadSync();
  const code = saved.code ? normalizeSyncCode(saved.code) : null;
  identity = { code: code ?? newCode(), deviceId: saved.deviceId ?? newDeviceId() };
  if (identity.code !== saved.code || identity.deviceId !== saved.deviceId) saveSync(identity);
  return identity;
}

/** Joins another code's account, or takes the PC's own device id; kept across restarts. */
export function setIdentity(next: SavedSync): void {
  identity = next;
  saveSync(next);
}

/** Sent with every API request: the account picks the alarms and to-do list (apps/api todos.py). */
export function syncHeaders(): Record<string, string> {
  const { code, deviceId } = ensureIdentity();
  return { [SYNC_CODE_HEADER]: code, [SYNC_DEVICE_HEADER]: deviceId };
}
