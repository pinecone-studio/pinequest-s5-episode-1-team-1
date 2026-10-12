import { Platform } from "react-native";
import { desktopBaseUrl } from "./connect";

const RETRY_MS = 5_000;

/** The key that calls BEKHI from any program, once the computer's API says it has one. */
let key: string | null = null;
export const wakeKey = () => key;

/**
 * In BEKHI's window on the computer: calls `onWake` each time the key that calls BEKHI
 * (Ctrl+Space, apps/api hotkey.py) is pressed anywhere; the window is brought to the front first.
 * Waits on the computer's API, one request at a time. Returns a function that stops waiting.
 */
export function onWakeKey(onWake: () => void): () => void {
  if (Platform.OS !== "web") return () => {};
  let stopped = false;
  void (async () => {
    let seen = -1;
    while (!stopped) {
      try {
        const res = await fetch(`${desktopBaseUrl()}/api/v1/desktop/wake?after=${seen}`);
        if (res.status === 404) return; // not BEKHI's own API on this computer: no key here
        if (!res.ok) throw new Error(`wake answered ${res.status}`);
        const body = (await res.json()) as { count: number; key: string | null };
        key = body.key;
        if (seen >= 0 && body.count > seen && !stopped) onWake();
        seen = body.count;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, RETRY_MS)); // the API restarting, or asleep
      }
    }
  })();
  return () => {
    stopped = true;
  };
}
