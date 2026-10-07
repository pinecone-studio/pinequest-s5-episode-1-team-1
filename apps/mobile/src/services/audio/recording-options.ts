import { AudioQuality, IOSOutputFormat, type RecordingOptions } from "expo-audio";
import { AUDIO_UPLOAD } from "@duud/contracts";

/** iOS records straight to the upload format (16 kHz mono 16-bit WAV). Web records
 *  WebM and is converted to the same WAV before upload (audio-upload.web.ts). */
export const VOICE_RECORDING: RecordingOptions = {
  extension: ".wav",
  sampleRate: AUDIO_UPLOAD.sample_rate_hz,
  numberOfChannels: AUDIO_UPLOAD.channels,
  bitRate: AUDIO_UPLOAD.sample_rate_hz * AUDIO_UPLOAD.bit_depth,
  isMeteringEnabled: true, // levels for end-of-speech detection (endpointing.ts)
  ios: {
    extension: ".wav",
    outputFormat: IOSOutputFormat.LINEARPCM,
    audioQuality: AudioQuality.MAX,
    linearPCMBitDepth: AUDIO_UPLOAD.bit_depth,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  android: { outputFormat: "mpeg4", audioEncoder: "aac" },
  web: { mimeType: "audio/webm" },
};
