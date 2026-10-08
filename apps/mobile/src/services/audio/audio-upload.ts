import { File } from "expo-file-system";
import { AUDIO_UPLOAD } from "@bekhi/contracts";

/**
 * Native: the recorder already wrote a 16 kHz mono WAV file.
 *
 * Since SDK 57 the global fetch is Expo's, which rejects React Native's `{ uri, name, type }`
 * file parts ("Unsupported FormDataPart implementation"). It reads any part that has a
 * `bytes()` method, using `name` and `type` for the part headers.
 */
export async function appendAudio(form: FormData, uri: string): Promise<void> {
  const file = new File(uri);
  const part = { name: "voice.wav", type: AUDIO_UPLOAD.mime_type, bytes: () => file.bytes() };
  form.append("audio", part as unknown as Blob);
}
