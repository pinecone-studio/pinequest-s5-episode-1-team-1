/** This browser's sync code and id. */
const STORAGE_KEY = "bekhi.sync";

export interface SavedSync {
  code: string;
  deviceId: string;
}

export function loadSync(): Partial<SavedSync> {
  try {
    return JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY) ?? "{}") as Partial<SavedSync>;
  } catch {
    return {};
  }
}

export function saveSync(value: SavedSync): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // private window or storage blocked: a new code is made on reload
  }
}
