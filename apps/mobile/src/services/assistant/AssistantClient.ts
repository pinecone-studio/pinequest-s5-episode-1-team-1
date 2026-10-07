import type {
  ActionResultsRequest,
  ActionResultsResponse,
  AssistantContext,
  AssistantTurn,
} from "@duud/contracts";

/**
 * - preview: no backend; plans a fixed set of sample phrases locally
 * - live:    FastAPI
 */
export interface AssistantClient {
  readonly mode: "preview" | "live";
  sendText(text: string, context: AssistantContext): Promise<AssistantTurn>;
  /**
   * Speech to text. `audioUri` is a recording made with VOICE_RECORDING options; only the
   * returned text goes on to the assistant (sendText). The audio is never stored.
   */
  transcribe(audioUri: string): Promise<string>;
  reportResults(req: ActionResultsRequest): Promise<ActionResultsResponse>;
}

/** Error carrying a Mongolian message that is safe to show the user. */
export class AssistantError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
  }
}
