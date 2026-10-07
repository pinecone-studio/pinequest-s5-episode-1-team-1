import { useCallback, useEffect, useRef } from "react";
import { requestRecordingPermissionsAsync, useAudioStream, type AudioStreamBuffer } from "expo-audio";
import { File, Paths } from "expo-file-system";
import { AUDIO_UPLOAD } from "@duud/contracts";
import { createEndpointer, type Verdict } from "./endpointing";
import { pcm16Wav } from "./wav";

export type StartResult = "recording" | "permission_denied" | "failed";

type Take = {
  chunks: Int16Array[];
  samples: number;
  rate: number;
  channels: number;
  endpoint: ReturnType<typeof createEndpointer>;
};

/**
 * Android version of useVoiceInput.ts, with the same behaviour. Android's recorder
 * (MediaRecorder) cannot write WAV, so the microphone is read as raw 16 kHz PCM and
 * saved as the same 16-bit WAV the iPhone uploads. The loudness of each ~100 ms buffer
 * (RMS in dBFS, like iOS averagePower) drives the same end-of-speech detection.
 */
export function useVoiceInput(
  onAutoStop: (uri: string | null) => void,
  onNoSpeech: (micSilent: boolean) => void,
  /** Each microphone reading in dBFS, e.g. for a level meter. */
  onLevel?: (db: number | undefined) => void,
) {
  const handlers = useRef({ onAutoStop, onNoSpeech, onLevel });
  handlers.current = { onAutoStop, onNoSpeech, onLevel };
  const take = useRef<Take | null>(null);
  const lastFile = useRef<File | null>(null);

  const { stream } = useAudioStream({
    sampleRate: AUDIO_UPLOAD.sample_rate_hz,
    channels: AUDIO_UPLOAD.channels,
    encoding: "int16",
    onBuffer: (buffer) => onBuffer(buffer),
  });

  /** Ends the recording; with `save`, writes it to a WAV file and returns its URI. */
  const finish = useCallback(
    (save: boolean): string | null => {
      const current = take.current;
      if (!current) return null;
      take.current = null;
      stream.stop();
      if (!save || current.samples === 0) return null;
      try {
        const pcm = new Int16Array(current.samples);
        let offset = 0;
        for (const chunk of current.chunks) {
          pcm.set(chunk, offset);
          offset += chunk.length;
        }
        const file = new File(Paths.cache, `duud-voice-${Date.now()}.wav`);
        file.write(pcm16Wav(pcm, current.rate, current.channels));
        lastFile.current = file;
        return file.uri;
      } catch (e) {
        console.warn("saving the recording failed", e);
        return null;
      }
    },
    [stream],
  );

  const stop = useCallback(async (): Promise<string | null> => finish(true), [finish]);

  function onBuffer(buffer: AudioStreamBuffer) {
    const current = take.current;
    if (!current) return; // arrived after stop()
    const chunk = new Int16Array(buffer.data.slice(0, buffer.data.byteLength - (buffer.data.byteLength % 2)));
    current.chunks.push(chunk);
    current.samples += chunk.length;
    current.rate = buffer.sampleRate;
    current.channels = buffer.channels;

    const level = rmsDb(chunk);
    handlers.current.onLevel?.(level);
    const elapsed = (current.samples / current.channels / current.rate) * 1000;
    const verdict: Verdict = elapsed >= AUDIO_UPLOAD.max_seconds * 1000 ? "done" : current.endpoint(level, elapsed);
    if (verdict === "done") handlers.current.onAutoStop(finish(true));
    else if (verdict === "no_speech" || verdict === "mic_silent") {
      finish(false);
      handlers.current.onNoSpeech(verdict === "mic_silent");
    }
  }

  const start = useCallback(async (): Promise<StartResult> => {
    if (take.current) return "recording";
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) return "permission_denied";
      // The previous recording was uploaded long ago; the audio itself is never kept.
      try {
        lastFile.current?.delete();
      } catch {
        // already gone; the cache is cleaned by the OS anyway
      }
      lastFile.current = null;
      take.current = {
        chunks: [],
        samples: 0,
        rate: AUDIO_UPLOAD.sample_rate_hz,
        channels: AUDIO_UPLOAD.channels,
        endpoint: createEndpointer(),
      };
      await stream.start();
      return "recording";
    } catch (e) {
      take.current = null;
      console.warn("recording failed to start", e);
      return "failed";
    }
  }, [stream]);

  useEffect(() => () => void finish(false), [finish]);

  return { start, stop };
}

/** Loudness of a buffer in dBFS (-160 for digital silence, as iOS reports it). */
function rmsDb(pcm: Int16Array): number {
  let sum = 0;
  for (const s of pcm) sum += s * s;
  const rms = pcm.length > 0 ? Math.sqrt(sum / pcm.length) : 0;
  return rms > 0 ? 20 * Math.log10(rms / 32768) : -160;
}
