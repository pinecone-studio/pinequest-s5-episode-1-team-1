import { Platform } from "react-native";
import { create } from "zustand";
import { MN, type ActionRequest, type ActionResult, type AssistantTurn } from "@bekhi/contracts";
import { toward } from "@/lib/mongolian";
import { AssistantError, type AssistantClient } from "@/services/assistant/AssistantClient";
import { PreviewAssistantClient } from "@/services/assistant/PreviewAssistantClient";
import { apiBaseUrl, connectAssistant } from "@/services/assistant/connect";
import { buildContext } from "@/services/assistant/context";
import { executeDeviceAction, iosActions, type ChosenContact } from "@/services/ios-actions";
import { findContacts, type ContactCandidate } from "@/services/ios-actions/contacts";
import { speak, stopSpeaking } from "@/services/speech/speak";
import { startAlarmSync } from "@/services/sync/alarm-sync";
import { fetchVoices, loadSavedVoice, saveVoice, type Voice } from "@/services/speech/voices";

export type Phase =
  | "idle"
  | "listening"
  | "processing"
  | "confirming"
  | "executing"
  | "success"
  | "unavailable" // the action could not be done (iOS limit, permission, browser) — explained in the reply
  | "error"; // transport / AI failure

export type Tone = "normal" | "warning" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "bekhi";
  text: string;
  tone: Tone;
  /** How BEKHI understood a spoken request, shown when it differs from what was heard. */
  understood?: string;
}

/** Before a call or message: who the phone found for the name the user said. */
export interface ContactChoice {
  /** Contact names, best first. */
  names: string[];
  /** One name stands out, so the screen just asks yes / no about it. */
  sure: boolean;
}

interface AssistantState {
  phase: Phase;
  messages: ChatMessage[];
  pendingTurn: AssistantTurn | null;
  /** Set while confirming a call or message, once the phone has looked up the contact. */
  contactChoice: ContactChoice | null;
  conversationId: string | null;
  client: AssistantClient;
  voiceReplies: boolean;
  speechError: string | null;
  /** A reply is being read aloud. */
  speaking: boolean;
  /** Hands-free: the user talked, so listen again after each spoken reply. */
  conversing: boolean;
  /** Increments when the screen should start the microphone (next turn of the conversation). */
  listenRequest: number;
  /** ElevenLabs voices offered by the backend; empty until connected. */
  voices: Voice[];
  /** The chosen voice id (the backend's default until the user picks one). */
  voiceId: string | null;
  connect(): Promise<void>;
  /** Pick a voice and hear a short sample in it. */
  chooseVoice(id: string): void;
  submitText(text: string): Promise<void>;
  startListening(): void;
  submitVoice(audioUri: string | null): Promise<void>;
  /** The microphone heard nobody: end the hands-free conversation (and say so if the mic gave no sound at all). */
  stopConversation(micSilent: boolean): void;
  /** Stop reading the reply aloud, and do not listen again afterwards. */
  stopReply(): void;
  answerConfirmation(yes: boolean): Promise<void>;
  /** Pick one of `contactChoice.names` by index, or null for none of them. */
  chooseContact(index: number | null): Promise<void>;
  toggleVoiceReplies(): void;
  fail(message: string): void;
}

const OK = new Set<ActionResult["status"]>(["succeeded", "handed_off"]);
/** Phases after which the conversation may continue by voice (not while confirming or busy). */
const LISTEN_AFTER = new Set<Phase>(["idle", "success", "unavailable"]);
let seq = 0;
let speechSeq = 0;
const msg = (role: ChatMessage["role"], text: string, tone: Tone = "normal", understood?: string): ChatMessage => ({
  id: `m${++seq}`,
  role,
  text,
  tone,
  understood,
});

/** Same words, ignoring case, punctuation and spacing. */
const sameWords = (a: string, b: string) => {
  const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  return norm(a) === norm(b);
};

export const useAssistant = create<AssistantState>((set, get) => {
  const push = (m: ChatMessage) => set({ messages: [...get().messages, m] });

  /** In a hands-free conversation, ask the screen to listen for the user's next turn. */
  function listenAgain() {
    const { conversing, phase } = get();
    if (conversing && LISTEN_AFTER.has(phase)) set({ listenRequest: get().listenRequest + 1 });
  }

  /**
   * Show a BEKHI reply and, if enabled, read it aloud. Speech problems never hide the text.
   * `thenListen`: the user may answer by voice once the reply has been spoken.
   */
  function reply(text: string, tone: Tone = "normal", thenListen = false) {
    if (!text) return;
    push(msg("bekhi", text, tone));
    if (!thenListen) set({ conversing: false });
    const { client, voiceReplies } = get();
    if (!voiceReplies || client.mode !== "live") {
      if (thenListen) listenAgain();
      return;
    }
    const mine = ++speechSeq;
    set({ speaking: true, speechError: null });
    speak(apiBaseUrl(), text, get().voiceId, showPaidVoiceNotice)
      .then((finished) => {
        if (finished && thenListen) listenAgain();
      })
      .catch((e) => {
        set({ speechError: e instanceof AssistantError ? e.message : "Дуу тоглуулж чадсангүй." });
        if (thenListen) listenAgain(); // the text is on screen; keep the conversation going
      })
      .finally(() => {
        if (mine === speechSeq) set({ speaking: false });
      });
  }

  function showPaidVoiceNotice() {
    const name = get().voices.find((v) => v.id === get().voiceId)?.name ?? "Энэ";
    set({ speechError: `${name} хоолой ElevenLabs-ийн төлбөртэй багц шаарддаг тул үндсэн хоолойгоор уншлаа.` });
  }

  /** The contacts found for the call or message waiting for an answer (numbers stay on the phone). */
  let found: { actionId: string; candidates: ContactCandidate[] } | null = null;

  async function runActions(turn: AssistantTurn, approved: boolean, chosen?: { actionId: string; contact: ChosenContact }) {
    set({ phase: "executing", pendingTurn: null, contactChoice: null });
    const results: ActionResult[] = [];
    for (const action of turn.actions) {
      if (action.result) {
        results.push(action.result);
      } else if (action.confirmation.required && !approved) {
        results.push({ action_id: action.id, tool: action.tool, status: "cancelled", executed_via: null, error_code: null });
      } else {
        results.push(await executeDeviceAction(iosActions, action, chosen?.actionId === action.id ? chosen.contact : undefined));
      }
    }
    const final = await get().client.reportResults({
      conversation_id: turn.conversation_id,
      turn_id: turn.turn_id,
      results,
    });
    const allOk = results.every((r) => OK.has(r.status));
    const phase: Phase = results.every((r) => r.status === "cancelled") ? "idle" : allOk ? "success" : "unavailable";
    set({ phase });
    reply(final.response, allOk || phase === "idle" ? "normal" : "warning", true);
  }

  async function handleTurn(turn: AssistantTurn) {
    set({ conversationId: turn.conversation_id });
    switch (turn.stage) {
      case "final": {
        const failed = turn.actions.some((a) => a.result && !OK.has(a.result.status));
        const limited = turn.limitations.length > 0 || failed;
        set({ phase: limited ? "unavailable" : turn.actions.length > 0 ? "success" : "idle" });
        reply(turn.response, limited ? "warning" : "normal", true);
        break;
      }
      case "awaiting_confirmation": {
        const contactAction = contactToFind(turn);
        if (contactAction) {
          await askWhichContact(turn, contactAction);
          break;
        }
        set({ phase: "confirming", pendingTurn: turn });
        reply(turn.response);
        break;
      }
      case "awaiting_device":
        await runActions(turn, true);
        break;
      case "awaiting_clarification":
        set({ phase: "idle" });
        reply(turn.clarification?.question ?? turn.response, "normal", true);
        break;
    }
  }

  /** A call or message that is the only thing waiting for a yes: the phone finds the contact first. */
  function contactToFind(turn: AssistantTurn): ActionRequest | null {
    if (Platform.OS === "web") return null;
    const asking = turn.actions.filter((a) => !a.result && a.confirmation.required);
    const [only] = asking;
    return asking.length === 1 && only && (only.tool === "call_contact" || only.tool === "send_message") ? only : null;
  }

  /**
   * Ask with the contact the phone actually found ("Anka руу залгах уу?"), or let the user pick
   * when several names are close: speech recognition often mishears names, and contacts are
   * saved in Latin letters. Nothing is dialled or sent before the user answers.
   */
  async function askWhichContact(turn: AssistantTurn, action: ActionRequest) {
    const args = action.arguments as { contact_name: string; name_spellings?: string[]; body?: string };
    const search = await findContacts(args.contact_name, args.name_spellings ?? []).catch((e: unknown) => {
      console.warn("contact search failed", e);
      return null;
    });
    if (search?.kind !== "candidates") {
      // Nobody to ask about: the action reports why (not found, no number, no permission).
      await runActions(turn, true, search?.kind === "not_found" ? { actionId: action.id, contact: null } : undefined);
      return;
    }
    found = { actionId: action.id, candidates: search.candidates };
    const names = search.candidates.map((c) => c.name);
    set({ phase: "confirming", pendingTurn: turn, contactChoice: { names, sure: search.sure } });
    const verb = action.tool === "call_contact" ? "залгах" : "бичих";
    const [first] = names;
    if (search.sure && first) {
      reply(action.tool === "call_contact" ? `${toward(first)} залгах уу?` : `${toward(first)} "${args.body ?? ""}" гэж бичих үү?`);
    } else {
      reply(`${names.join(", ")}. Аль рүү нь ${verb} вэ?`);
    }
  }

  async function guarded(work: () => Promise<void>) {
    try {
      await work();
    } catch (e) {
      console.warn("assistant turn failed", e);
      set({ phase: "error", pendingTurn: null, contactChoice: null });
      reply(e instanceof AssistantError ? e.message : MN.errors.llm, "error");
    }
  }

  return {
    phase: "idle",
    messages: [],
    pendingTurn: null,
    contactChoice: null,
    conversationId: null,
    client: new PreviewAssistantClient(),
    voiceReplies: true,
    speechError: null,
    speaking: false,
    conversing: false,
    listenRequest: 0,
    voices: [],
    voiceId: null,

    async connect() {
      const client = await connectAssistant();
      set({ client });
      if (client.mode !== "live") return;
      // Alarms and timers set on the user's other devices ring here too.
      startAlarmSync();
      const list = await fetchVoices(apiBaseUrl());
      if (!list) return;
      const saved = loadSavedVoice();
      set({ voices: list.voices, voiceId: list.voices.some((v) => v.id === saved) ? saved : list.default });
    },

    chooseVoice(id) {
      const voice = get().voices.find((v) => v.id === id);
      if (!voice) return;
      saveVoice(id);
      set({ voiceId: id, speechError: null });
      if (get().client.mode !== "live") return;
      const mine = ++speechSeq;
      set({ speaking: true });
      speak(apiBaseUrl(), "Сайн байна уу, би БЭХИ байна.", id, showPaidVoiceNotice)
        .catch((e) => set({ speechError: e instanceof AssistantError ? e.message : "Дуу тоглуулж чадсангүй." }))
        .finally(() => {
          if (mine === speechSeq) set({ speaking: false });
        });
    },

    async submitText(text) {
      const trimmed = text.trim();
      if (!trimmed) return;
      stopSpeaking();
      push(msg("user", trimmed));
      set({ phase: "processing", pendingTurn: null, contactChoice: null, conversing: false });
      await guarded(async () => handleTurn(await get().client.sendText(trimmed, buildContext(get().conversationId))));
    },

    startListening() {
      stopSpeaking();
      set({ phase: "listening", pendingTurn: null, contactChoice: null });
    },

    stopReply() {
      set({ conversing: false });
      stopSpeaking();
    },

    stopConversation(micSilent) {
      if (micSilent) {
        set({ conversing: false, phase: "error" });
        reply("Микрофоноос дуу огт орж ирэхгүй байна. Микрофон тань дуугүй (mute) болсон эсэхийг шалгана уу.", "error");
        return;
      }
      set({ conversing: false, phase: get().phase === "listening" ? "idle" : get().phase });
    },

    async submitVoice(audioUri) {
      if (!audioUri) {
        set({ phase: "error" });
        reply(MN.errors.stt, "error");
        return;
      }
      set({ phase: "processing", conversing: true });
      await guarded(async () => {
        // Speech -> text first; only the text goes on to the assistant.
        const text = await get().client.transcribe(audioUri);
        const said = msg("user", text);
        push(said);
        const turn = await get().client.sendText(text, buildContext(get().conversationId));
        if (turn.summary && !sameWords(turn.summary, text)) {
          set({ messages: get().messages.map((m) => (m.id === said.id ? { ...m, understood: turn.summary ?? undefined } : m)) });
        }
        await handleTurn(turn);
      });
    },

    async answerConfirmation(yes) {
      const turn = get().pendingTurn;
      if (!turn) return;
      push(msg("user", yes ? MN.ui.confirmYes : MN.ui.confirmNo));
      const picked = found;
      found = null;
      const chosen = yes && picked ? { actionId: picked.actionId, contact: picked.candidates[0] ?? null } : undefined;
      await guarded(() => runActions(turn, yes, chosen));
    },

    async chooseContact(index) {
      const turn = get().pendingTurn;
      const picked = found;
      if (!turn || !picked) return;
      found = null;
      const contact = index === null ? undefined : picked.candidates[index];
      push(msg("user", contact?.name ?? MN.ui.confirmNo));
      await guarded(() => runActions(turn, !!contact, contact ? { actionId: picked.actionId, contact } : undefined));
    },

    toggleVoiceReplies() {
      if (get().voiceReplies) stopSpeaking();
      set({ voiceReplies: !get().voiceReplies, speechError: null });
    },

    fail(message) {
      set({ phase: "error", pendingTurn: null, contactChoice: null });
      reply(message, "error");
    },
  };
});
