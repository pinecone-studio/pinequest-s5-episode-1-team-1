import { Linking, Platform } from "react-native";
import { apiBaseUrl } from "@/services/assistant/connect";
import { syncHeaders } from "@/services/sync/identity";

/**
 * Gmail for this account (apps/api google_link.py): linked once with Google sign-in, then BEKHI can
 * check and read the mail. Every device with the same sync code uses the same link.
 */
export interface GoogleStatus {
  available: boolean;
  linked: boolean;
  email: string | null;
  /** May write and send mail (linked after BEKHI could answer mail). */
  send?: boolean;
}

/**
 * The draft card's buttons: send the Gmail draft BEKHI wrote, or throw it away. Resolves to an error
 * message to show, or null.
 */
export async function finishDraft(draftId: string, what: "send" | "delete"): Promise<string | null> {
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/google/drafts/${encodeURIComponent(draftId)}/${what}`, {
      method: "POST",
      headers: syncHeaders(),
    });
    if (res.ok) return null;
    const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
    return body?.error?.message ?? "Gmail-тэй холбогдож чадсангүй.";
  } catch {
    return "Сервертэй холбогдож чадсангүй.";
  }
}

export async function googleStatus(): Promise<GoogleStatus | null> {
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/auth/google`, { headers: syncHeaders() });
    return res.ok ? ((await res.json()) as GoogleStatus) : null;
  } catch {
    return null;
  }
}

/**
 * Opens Google's sign-in page. In a browser the window opens at the tap (or it would be blocked) and
 * gets its address once the API answers. Resolves to an error message to show, or null.
 */
export async function linkGoogle(): Promise<string | null> {
  const popup = Platform.OS === "web" && typeof window !== "undefined" ? window.open("", "_blank", "width=480,height=680") : null;
  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/auth/google/start`, { method: "POST", headers: syncHeaders() });
    const body = (await res.json().catch(() => null)) as { url?: string; error?: { message?: string } } | null;
    if (!res.ok || !body?.url) {
      popup?.close();
      return body?.error?.message ?? "Google холболтыг эхлүүлж чадсангүй.";
    }
    if (popup) popup.location.href = body.url;
    else await Linking.openURL(body.url);
    return null;
  } catch {
    popup?.close();
    return "Сервертэй холбогдож чадсангүй.";
  }
}

export async function unlinkGoogle(): Promise<void> {
  await fetch(`${apiBaseUrl()}/api/v1/auth/google/unlink`, { method: "POST", headers: syncHeaders() }).catch(() => undefined);
}
