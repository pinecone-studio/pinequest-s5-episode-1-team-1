import { ApiError, DirectionsResponse, type DirectionsRequest } from "@bekhi/contracts";
import { apiBaseUrl } from "@/services/assistant/connect";

const TIMEOUT_MS = 20_000;
const MN_FAILED = "Уучлаарай, зам тооцоолоход алдаа гарлаа.";
const MN_OFFLINE = "Сервертэй холбогдож чадсангүй. Интернэтээ шалгаад дахин оролдоно уу.";

/** A route from the backend (Google Routes API). Throws an Error with a Mongolian message. */
export async function fetchDirections(req: DirectionsRequest): Promise<DirectionsResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl()}/api/v1/maps/directions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
      signal: controller.signal,
    });
  } catch (e) {
    console.warn("directions request failed", e);
    throw new Error(MN_OFFLINE);
  } finally {
    clearTimeout(timer);
  }
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const err = ApiError.safeParse(json);
    throw new Error(err.success ? err.data.error.message : MN_FAILED);
  }
  // A response that does not match the contract is never drawn.
  const route = DirectionsResponse.safeParse(json);
  if (!route.success) throw new Error(MN_FAILED);
  return route.data;
}
