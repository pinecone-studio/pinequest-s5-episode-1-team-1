import {
  AssistantTurn,
  type ActionRequest,
  type ActionResultsRequest,
  type ActionResultsResponse,
  type AssistantContext,
  type Limitation,
} from "@bekhi/contracts";
import { toLocalIso, tomorrowAt } from "@/lib/time";
import { AssistantError, type AssistantClient } from "./AssistantClient";
import { composeOutcome } from "./compose-outcome";

/**
 * Stand-in for the backend until Phase 3. It does NOT understand language: it only
 * knows the sample phrases below, and builds the same AssistantTurn the backend
 * will return. Every turn is validated with the shared contract, like live ones.
 */
export const SAMPLE_PHRASES = [
  "Маргааш 9 цагт ажилтайг минь сануулаарай.",
  "Ээж рүүгээ залга.",
  "Сүхбаатарын талбай руу явъя.",
  "Батад орой уулзъя гэж бич.",
  "Wi-Fi асаа.",
] as const;

type Plan = {
  intent: string;
  response: string;
  actions: ActionRequest[];
  limitations?: Limitation[];
};

const noConfirm = { required: false, prompt: null };

function plan(text: string, ctx: AssistantContext): Plan | null {
  switch (text) {
    case SAMPLE_PHRASES[0]:
      return {
        intent: "create_reminder",
        response: "",
        actions: [
          {
            id: "a1",
            tool: "create_reminder",
            arguments: { title: "Ажилтай", due_at: toLocalIso(tomorrowAt(9)), timezone: ctx.timezone },
            confirmation: noConfirm,
            result: null,
          },
        ],
      };
    case SAMPLE_PHRASES[1]: {
      const prompt = "Ээж рүү тань залгах уу?";
      return {
        intent: "call_contact",
        response: prompt,
        actions: [
          {
            id: "a1",
            tool: "call_contact",
            arguments: { contact_name: "Ээж" },
            confirmation: { required: true, prompt },
            result: null,
          },
        ],
      };
    }
    case SAMPLE_PHRASES[2]:
      return {
        intent: "open_maps",
        response: "",
        actions: [
          {
            id: "a1",
            tool: "open_maps",
            arguments: { destination: "Сүхбаатарын талбай", mode: "driving" },
            confirmation: noConfirm,
            result: null,
          },
        ],
      };
    case SAMPLE_PHRASES[3]: {
      const prompt = "Батад 'орой уулзъя' гэж мессеж явуулах уу?";
      return {
        intent: "send_message",
        response: prompt,
        actions: [
          {
            id: "a1",
            tool: "send_message",
            arguments: { contact_name: "Бат", body: "Орой уулзъя" },
            confirmation: { required: true, prompt },
            result: null,
          },
        ],
      };
    }
    case SAMPLE_PHRASES[4]:
      return {
        intent: "unsupported",
        response:
          "Уучлаарай, iPhone апп-д Wi-Fi-г асаах, унтраахыг зөвшөөрдөггүй. Control Center-оос асаах эсвэл Shortcuts дээр 'Set Wi-Fi' үйлдэлтэй shortcut үүсгэж болно.",
        actions: [],
        limitations: [
          {
            code: "system_settings_toggle",
            message: "iPhone апп-д Wi-Fi-г асаах, унтраахыг зөвшөөрдөггүй.",
            alternative: { kind: "shortcut", description: "Shortcuts дээр 'Set Wi-Fi' үйлдэлтэй shortcut үүсгэж болно." },
          },
        ],
      };
    default:
      return null;
  }
}

export class PreviewAssistantClient implements AssistantClient {
  readonly mode = "preview" as const;
  private readonly turns = new Map<string, { actions: ActionRequest[]; nowIso: string }>();

  async sendText(text: string, ctx: AssistantContext): Promise<AssistantTurn> {
    await delay(700);
    const p = plan(text, ctx) ?? {
      intent: "chitchat",
      response: "Одоохондоо жишээ өгүүлбэрүүдийг л ойлгоно. Backend холбогдсоны дараа чөлөөтэй ярьж болно.",
      actions: [],
    };
    const needsConfirm = p.actions.some((a) => a.confirmation.required);
    const turn = AssistantTurn.parse({
      conversation_id: ctx.conversation_id ?? uuid(),
      turn_id: uuid(),
      transcript: text,
      intent: p.intent,
      stage: needsConfirm ? "awaiting_confirmation" : p.actions.length > 0 ? "awaiting_device" : "final",
      response: p.response,
      actions: p.actions,
      requires_confirmation: needsConfirm,
      requires_clarification: false,
      clarification: null,
      limitations: p.limitations ?? [],
      audio_url: null,
    });
    this.turns.set(turn.turn_id, { actions: turn.actions, nowIso: ctx.client_now });
    return turn;
  }

  async transcribe(): Promise<string> {
    throw new AssistantError(
      "Backend асаагүй байгаа тул дууг ойлгох боломжгүй. Backend-ээ асаагаад дахин оролдоорой.",
      "preview",
    );
  }

  async reportResults(req: ActionResultsRequest): Promise<ActionResultsResponse> {
    const turn = this.turns.get(req.turn_id);
    this.turns.delete(req.turn_id);
    return {
      conversation_id: req.conversation_id,
      turn_id: req.turn_id,
      response: turn ? composeOutcome(turn.actions, req.results, turn.nowIso) : "",
      audio_url: null,
    };
  }
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** RFC 4122 v4 — preview ids only; the backend issues real ids. */
function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
