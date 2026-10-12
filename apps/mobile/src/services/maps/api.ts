import { ApiError } from "@bekhi/contracts";
import { apiBaseUrl } from "@/services/assistant/connect";

const TIMEOUT_MS = 20_000;
const MN_OFFLINE =
  "Сервертэй холбогдож чадсангүй. Интернэтээ шалгаад дахин оролдоно уу.";

/** The part of a contract schema used here. */
type Schema<T> = {
  safeParse(value: unknown): { success: true; data: T } | { success: false };
};

/** POST to a backend maps endpoint. Throws an Error with a Mongolian message. */
export async function postMaps<T>(
  path: string,
  body: unknown,
  schema: Schema<T>,
  failedMessage: string,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl()}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (e) {
    console.warn("maps request failed", path, e);
    throw new Error(MN_OFFLINE);
  } finally {
    clearTimeout(timer);
  }
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = ApiError.safeParse(json);
    throw new Error(err.success ? err.data.error.message : failedMessage);
  }
  // A response that does not match the contract is never shown.
  const parsed = schema.safeParse(json);
  if (!parsed.success) throw new Error(failedMessage);
  return parsed.data;
}
