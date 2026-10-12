import type { BriefingPart } from "@bekhi/contracts";
import { apiBaseUrl } from "@/services/assistant/connect";
import { syncHeaders } from "@/services/sync/identity";

/**
 * Who the user is to BEKHI (apps/api profile.py), the same on every device with this sync code:
 * their name, their city and what the day's briefing tells. Also set by voice ("Намайг Нандин гэдэг").
 */
export interface Profile {
  name: string | null;
  city: string | null;
  /** null until the user chooses: the briefing then tells DEFAULT_BRIEFING and asks. */
  briefing: BriefingPart[] | null;
}

export const DEFAULT_BRIEFING: BriefingPart[] = ["weather", "todos", "schedule"];
export const BRIEFING_PARTS: { part: BriefingPart; label: string }[] = [
  { part: "weather", label: "Цаг агаар" },
  { part: "todos", label: "Хийх зүйлс" },
  { part: "schedule", label: "Товлосон" },
  { part: "email", label: "Имэйл" },
  { part: "news", label: "Мэдээ" },
];

export async function loadProfile(): Promise<Profile | null> {
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/profile`, { headers: syncHeaders() });
    return res.ok ? ((await res.json()) as Profile) : null;
  } catch {
    return null;
  }
}

/** Changes the given fields ("" drops a name or city); resolves to the profile saved, or null. */
export async function saveProfile(changes: Partial<Profile>): Promise<Profile | null> {
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/profile`, {
      method: "POST",
      headers: { ...syncHeaders(), "content-type": "application/json" },
      body: JSON.stringify(changes),
    });
    return res.ok ? ((await res.json()) as Profile) : null;
  } catch {
    return null;
  }
}
