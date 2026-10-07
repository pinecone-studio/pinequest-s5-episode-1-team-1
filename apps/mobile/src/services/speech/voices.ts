export interface Voice {
  id: string;
  name: string;
  gender: string;
  /** A Voice Library voice: on a free ElevenLabs plan the default voice reads instead. */
  needs_paid_plan: boolean;
}

export interface VoiceList {
  default: string;
  voices: Voice[];
}

/** The voices the backend offers (GET /assistant/voices). */
export async function fetchVoices(baseUrl: string): Promise<VoiceList | null> {
  try {
    const res = await fetch(`${baseUrl}/api/v1/assistant/voices`);
    if (!res.ok) return null;
    const body = (await res.json()) as VoiceList;
    return Array.isArray(body?.voices) && typeof body.default === "string" ? body : null;
  } catch {
    return null;
  }
}

export { loadSavedVoice, saveVoice } from "./voice-storage";
