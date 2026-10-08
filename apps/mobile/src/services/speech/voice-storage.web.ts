/** The chosen voice, remembered by the browser. */
const STORAGE_KEY = "bekhi.voice";

export function loadSavedVoice(): string | null {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function saveVoice(id: string): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, id);
  } catch {
    // private window or storage blocked: the choice lasts until reload
  }
}
