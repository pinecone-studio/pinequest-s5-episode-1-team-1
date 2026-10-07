import { createAudioPlayer, setAudioModeAsync } from "expo-audio";
import { File, Paths } from "expo-file-system";
import { requestSpeech, VOICE_FALLBACK_HEADER } from "./request-speech";

/** How long to wait for the audio to load before giving up on it. */
const LOAD_TIMEOUT_MS = 8_000;

let current: { stop(): void } | null = null;
let generation = 0;

/**
 * Plays the spoken reply and resolves when it has finished, so the caller can start
 * listening again. Resolves false if it was stopped or replaced by a newer reply.
 * `onVoiceFallback`: the chosen voice needs a paid plan, so the default voice reads it.
 */
export async function speak(
  baseUrl: string,
  text: string,
  voice: string | null = null,
  onVoiceFallback?: () => void,
): Promise<boolean> {
  stopSpeaking();
  const mine = ++generation;
  const res = await requestSpeech(baseUrl, text, voice);
  if (res.headers.get(VOICE_FALLBACK_HEADER) !== null) onVoiceFallback?.();
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (mine !== generation) return false;

  const ext = (res.headers.get("content-type") ?? "").includes("wav") ? "wav" : "mp3";
  const file = new File(Paths.cache, `duud-reply-${mine}.${ext}`);
  file.write(bytes);
  // Recording leaves the iOS session in play-and-record mode, which plays through the
  // earpiece. Switch back so the reply comes out of the loudspeaker.
  await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
  if (mine !== generation) {
    file.delete();
    return false;
  }

  const player = createAudioPlayer({ uri: file.uri });
  await new Promise<void>((resolve) => {
    let guard = setTimeout(stop, LOAD_TIMEOUT_MS);
    const sub = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) return stop();
      if (status.isLoaded && status.duration > 0) {
        // Loaded: allow the rest of the clip plus a margin, in case the finish event never comes.
        clearTimeout(guard);
        guard = setTimeout(stop, (status.duration - status.currentTime + 2) * 1000);
      }
    });
    let stopped = false;
    function stop() {
      if (stopped) return;
      stopped = true;
      clearTimeout(guard);
      sub.remove();
      player.pause();
      player.remove();
      try {
        file.delete();
      } catch {
        // cache files are cleaned up by the OS anyway
      }
      if (current === handle) current = null;
      resolve();
    }
    const handle = { stop };
    current = handle;
    player.play();
  });
  return mine === generation; // false when stopSpeaking() cut it off
}

export function stopSpeaking(): void {
  generation++;
  current?.stop();
}
