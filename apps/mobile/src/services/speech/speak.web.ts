import { AssistantError } from "@/services/assistant/AssistantClient";
import { requestSpeech, VOICE_FALLBACK_HEADER } from "./request-speech";

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
  const blob = await res.blob();
  if (mine !== generation) return false;

  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  await new Promise<void>((resolve, reject) => {
    let stopped = false;
    const stop = (error?: unknown) => {
      if (stopped) return;
      stopped = true;
      audio.pause();
      URL.revokeObjectURL(url);
      if (current === handle) current = null;
      if (error) reject(error);
      else resolve();
    };
    const handle = { stop: () => stop() };
    current = handle;
    audio.onended = () => stop();
    audio.onerror = () => stop(new AssistantError("Дуу тоглуулж чадсангүй.", "tts"));
    audio.play().catch(() =>
      // Autoplay policy: the browser wants a click on the page before it plays sound.
      stop(new AssistantError("Browser дуу тоглуулахыг зөвшөөрсөнгүй. Хуудас дээр нэг дараад дахин оролдоорой.", "tts")),
    );
  });
  return mine === generation; // false when stopSpeaking() cut it off
}

export function stopSpeaking(): void {
  generation++;
  current?.stop();
}
