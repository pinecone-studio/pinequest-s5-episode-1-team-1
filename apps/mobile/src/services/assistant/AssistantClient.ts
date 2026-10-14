import type {
  ActionResultsRequest,
  ActionResultsResponse,
  AssistantContext,
  AssistantTurn,
} from "@bekhi/contracts";
import type { PickedFile } from "@/services/documents/pick";

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
  /** Checks a contract before it is signed: one PDF or Word file, or photos of its pages. */
  checkDocument(files: PickedFile[], context: AssistantContext): Promise<AssistantTurn>;
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
