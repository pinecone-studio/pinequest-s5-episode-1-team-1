import { ApiError } from "@duud/contracts";
import { AssistantError } from "@/services/assistant/AssistantClient";

const TIMEOUT_MS = 20_000;

/** Response header: the chosen voice needs a paid ElevenLabs plan, so the default voice was used. */
export const VOICE_FALLBACK_HEADER = "x-duud-voice-fallback";

/**
 * Asks the backend to synthesize `text` (the TTS keys never reach the app) in `voice`
 * (an id from GET /assistant/voices, null for the default).
 * The body is MP3 from ElevenLabs or WAV from the Gemini fallback; see `content-type`.
 */
export async function requestSpeech(baseUrl: string, text: string, voice: string | null): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${baseUrl}/api/v1/assistant/tts`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, voice }),
      signal: controller.signal,
    });
  } catch {
    throw new AssistantError("Хариуг дуугаар уншихад сервертэй холбогдож чадсангүй.", "tts");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const err = ApiError.safeParse(await res.json().catch(() => null));
    throw new AssistantError(err.success ? err.data.error.message : "Дуу үүсгэхэд алдаа гарлаа.", "tts");
  }
  return res;
}
