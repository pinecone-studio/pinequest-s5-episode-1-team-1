import {
  ActionResultsResponse,
  ApiError,
  AssistantTurn,
  MN,
  type ActionResultsRequest,
  type AssistantContext,
} from "@bekhi/contracts";
import { appendAudio } from "@/services/audio/audio-upload";
import { syncHeaders } from "@/services/sync/identity";
import { AssistantError, type AssistantClient } from "./AssistantClient";

const TIMEOUT_MS = 30_000;

/** FastAPI client. Every response is validated with the shared contract before use. */
export class HttpAssistantClient implements AssistantClient {
  readonly mode = "live" as const;

  constructor(private readonly baseUrl: string) {}

  async sendText(text: string, context: AssistantContext) {
    const body = await this.post("/api/v1/assistant/chat", {
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, context }),
    });
    return parseOrThrow(AssistantTurn, body);
  }

  async transcribe(audioUri: string) {
    const form = new FormData();
    await appendAudio(form, audioUri);
    const body = await this.post("/api/v1/assistant/transcribe", { body: form });
    const transcript = (body as { transcript?: unknown } | null)?.transcript;
    if (typeof transcript !== "string" || !transcript.trim()) throw new AssistantError(MN.errors.stt, "stt");
    return transcript.trim();
  }

  async reportResults(req: ActionResultsRequest) {
    const body = await this.post("/api/v1/assistant/actions/results", {
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
    return parseOrThrow(ActionResultsResponse, body);
  }

  private async post(path: string, init: RequestInit): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    let res: Response;
    try {
      // The sync code tells the API whose to-do list this is (apps/api todos.py).
      const headers = { ...syncHeaders(), ...(init.headers as Record<string, string> | undefined) };
      res = await fetch(this.baseUrl + path, { ...init, headers, method: "POST", signal: controller.signal });
    } catch (e) {
      console.warn(`request ${path} failed`, e); // the real cause, for the dev server log
      throw new AssistantError("Сервертэй холбогдож чадсангүй. Интернэтээ шалгаад дахин оролдоно уу.", "network");
    } finally {
      clearTimeout(timer);
    }
    const json: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const err = ApiError.safeParse(json);
      throw new AssistantError(err.success ? err.data.error.message : MN.errors.llm, err.success ? err.data.error.code : "http");
    }
    return json;
  }
}

function parseOrThrow<T>(schema: { safeParse(v: unknown): { success: true; data: T } | { success: false } }, value: unknown): T {
  const parsed = schema.safeParse(value);
  // A response that does not match the contract is never acted on.
  if (!parsed.success) throw new AssistantError(MN.errors.llm, "contract");
  return parsed.data;
}
