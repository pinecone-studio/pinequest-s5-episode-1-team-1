import { useCallback, useEffect, useRef } from "react";
import { Platform } from "react-native";
import { requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder } from "expo-audio";
import { AUDIO_UPLOAD } from "@duud/contracts";
import { createEndpointer } from "./endpointing";
import { VOICE_RECORDING } from "./recording-options";

export type StartResult = "recording" | "permission_denied" | "failed";

const POLL_MS = 100;

/**
 * Microphone recorder. start() asks for the permission the first time. Recording ends
 * when the user taps stop (stop() returns the URI), when they go quiet after speaking
 * (onAutoStop), or after AUDIO_UPLOAD.max_seconds. If nobody speaks, the recording is
 * dropped and onNoSpeech is called (micSilent: the input was dead silent, e.g. muted mic).
 */
export function useVoiceInput(
  onAutoStop: (uri: string | null) => void,
  onNoSpeech: (micSilent: boolean) => void,
  /** Each microphone reading in dBFS (undefined where metering is not available), e.g. for a level meter. */
  onLevel?: (db: number | undefined) => void,
) {
  const recorder = useAudioRecorder(VOICE_RECORDING);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);
  const active = useRef(false);
  const handlers = useRef({ onAutoStop, onNoSpeech, onLevel });
  handlers.current = { onAutoStop, onNoSpeech, onLevel };

  const stop = useCallback(async (): Promise<string | null> => {
    if (poll.current) clearInterval(poll.current);
    poll.current = null;
    if (!active.current) return null;
    active.current = false;
    try {
      await recorder.stop();
      return recorder.uri ?? null;
    } catch {
      return null;
    }
  }, [recorder]);

  const start = useCallback(async (): Promise<StartResult> => {
    if (active.current) return "recording";
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) return "permission_denied";
      if (Platform.OS !== "web") {
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      }
      await recorder.prepareToRecordAsync();
      recorder.record();
      active.current = true;

      const endpoint = createEndpointer();
      const startedAt = Date.now();
      poll.current = setInterval(() => {
        const elapsed = Date.now() - startedAt;
        const level = recorder.getStatus().metering;
        handlers.current.onLevel?.(level);
        const verdict = elapsed >= AUDIO_UPLOAD.max_seconds * 1000 ? "done" : endpoint(level, elapsed);
        if (verdict === "done") void stop().then((uri) => handlers.current.onAutoStop(uri));
        else if (verdict === "no_speech" || verdict === "mic_silent")
          void stop().then(() => handlers.current.onNoSpeech(verdict === "mic_silent"));
      }, POLL_MS);
      return "recording";
    } catch (e) {
      console.warn("recording failed to start", e);
      return "failed";
    }
  }, [recorder, stop]);

  useEffect(() => () => void stop(), [stop]);

  return { start, stop };
}
