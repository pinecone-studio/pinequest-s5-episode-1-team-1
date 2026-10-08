import { AUDIO_UPLOAD } from "@bekhi/contracts";
import { pcm16Wav } from "./wav";

/**
 * Web: MediaRecorder produces WebM/Opus, which the backend does not accept.
 * Decode it, downmix + resample to 16 kHz mono, and encode 16-bit PCM WAV.
 */
export async function appendAudio(form: FormData, uri: string): Promise<void> {
  const recorded = await (await fetch(uri)).arrayBuffer();
  const decoded = await new AudioContext().decodeAudioData(recorded);

  const rate = AUDIO_UPLOAD.sample_rate_hz;
  const frames = Math.max(1, Math.ceil(decoded.duration * rate));
  const offline = new OfflineAudioContext(1, frames, rate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();

  const pcm = Int16Array.from(rendered.getChannelData(0), (s) => {
    const clamped = Math.max(-1, Math.min(1, s));
    return clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  });
  form.append("audio", new Blob([pcm16Wav(pcm, rate)], { type: AUDIO_UPLOAD.mime_type }), "voice.wav");
}
