import { BriefingPart, type ActionResult } from "@bekhi/contracts";
import { localDate } from "@/lib/time";

/**
 * What a reply is about, laid out under BEKHI's words (components/ResultCards.tsx): the to-do list,
 * the weather, the mail, what is scheduled. Read from the actions' results; anything unexpected in
 * them is left out rather than shown wrong.
 */
export type Card =
  | { kind: "todos"; items: { title: string; due_at: string | null; done: boolean }[] }
  | { kind: "weather"; place: string; date: string; max: number; min: number; rain: number | null; condition: string; code: number | null }
  | { kind: "emails"; emails: { from: string; subject: string; snippet: string; unread: boolean }[] }
  | { kind: "email"; subject: string; from: string; text: string }
  | { kind: "scheduled"; items: { title: string; kind: string; fire_at: string }[] }
  | { kind: "news"; items: { title: string; url: string; source: string }[] }
  /** A Gmail draft BEKHI wrote (draft_email): sent only with the user's yes or the card's Send. */
  | { kind: "email_draft"; draftId: string; to: string; address: string; subject: string; body: string }
  /** Which window BEKHI looked at to answer (look_at_screen). */
  | { kind: "screen"; window: string }
  /** The briefing asks what to tell from now on: the parts it told this time are picked. */
  | { kind: "briefing_choice"; parts: BriefingPart[] }
  /** A contract checked before signing (check_document): errors first, then warnings. */
  | { kind: "document_check"; title: string; name: string; findings: DocumentFinding[] };

export interface DocumentFinding {
  severity: "error" | "warning";
  text: string;
  clause: string;
  /** Every place it is about (all the blanks left unfilled); the text names the first few. */
  items: string[];
}

type Data = Record<string, unknown>;

const isText = (v: unknown): v is string => typeof v === "string";
const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const list = (v: unknown): Data[] => (Array.isArray(v) ? v.filter((x): x is Data => typeof x === "object" && x !== null) : []);

function todos(v: unknown): Card | null {
  const items = list(v)
    .filter((i) => isText(i.title))
    .map((i) => ({ title: i.title as string, due_at: isText(i.due_at) ? i.due_at : null, done: i.done === true }));
  return items.length > 0 ? { kind: "todos", items } : null;
}

function weather(d: Data): Card | null {
  if (!isText(d.place) || !isText(d.date) || !isNumber(d.temp_max_c) || !isNumber(d.temp_min_c)) return null;
  return {
    kind: "weather",
    place: d.place,
    date: d.date,
    max: d.temp_max_c,
    min: d.temp_min_c,
    rain: isNumber(d.precipitation_probability) ? d.precipitation_probability : null,
    condition: isText(d.condition) ? d.condition : "",
    code: isNumber(d.weather_code) ? d.weather_code : null,
  };
}

function emails(v: unknown): Card | null {
  const items = list(v)
    .filter((e) => isText(e.from) || isText(e.subject))
    .map((e) => ({
      from: isText(e.from) ? e.from : "",
      subject: isText(e.subject) ? e.subject : "",
      snippet: isText(e.snippet) ? e.snippet : "",
      unread: e.unread === true,
    }));
  return items.length > 0 ? { kind: "emails", emails: items } : null;
}

function news(v: unknown): Card | null {
  const items = list(v)
    .filter((i) => isText(i.title) && isText(i.url) && /^https?:\/\//.test(i.url))
    .map((i) => ({ title: i.title as string, url: i.url as string, source: isText(i.source) ? i.source : "" }));
  return items.length > 0 ? { kind: "news", items } : null;
}

function documentCheck(d: Data): Card {
  const findings = list(d.findings)
    .filter((f) => isText(f.text) && f.text.trim())
    .map((f) => ({
      severity: f.severity === "error" ? ("error" as const) : ("warning" as const),
      text: f.text as string,
      clause: isText(f.clause) ? f.clause : "",
      items: Array.isArray(f.items) ? f.items.filter((i): i is string => isText(i) && i.trim() !== "") : [],
    }));
  return {
    kind: "document_check",
    title: isText(d.title) && d.title ? d.title : "Баримт",
    name: isText(d.name) ? d.name : "",
    findings,
  };
}

/** The parts a briefing told (its `parts`), or null when it does not say. */
function briefingParts(d: Data): BriefingPart[] | null {
  const parsed = BriefingPart.array().safeParse(d.parts);
  return parsed.success ? parsed.data : null;
}

const present = (c: Card | null): c is Card => c !== null;

function cardsOf(r: ActionResult, briefing: BriefingPart[] | "none"): Card[] {
  const d = r.data;
  if (r.status !== "succeeded" || !d) return [];
  switch (r.tool) {
    case "list_todos":
      return [todos(d.items)].filter(present);
    case "get_weather":
      return [weather(d)].filter(present);
    case "daily_briefing": {
      const w = typeof d.weather === "object" && d.weather !== null ? weather(d.weather as Data) : null;
      const ask: Card | null = isText(d.ask_mn) ? { kind: "briefing_choice", parts: briefingParts(d) ?? [] } : null;
      return [w, todos(d.todos), emails(d.emails), news(d.news), ask].filter(present);
    }
    case "check_email":
      return [emails(d.emails)].filter(present);
    case "draft_email":
      return isText(d.draft_id) && isText(d.body)
        ? [{
            kind: "email_draft",
            draftId: d.draft_id,
            to: isText(d.to) ? d.to : "",
            address: isText(d.to_address) ? d.to_address : "",
            subject: isText(d.subject) ? d.subject : "",
            body: d.body,
          }]
        : [];
    case "check_document":
      return [documentCheck(d)];
    case "look_at_screen":
      return isText(d.window) && d.window ? [{ kind: "screen", window: d.window }] : [];
    case "read_email":
      return isText(d.text) && d.text.trim()
        ? [{ kind: "email", subject: isText(d.subject) ? d.subject : "", from: isText(d.from) ? d.from : "", text: d.text }]
        : [];
    case "list_reminders": {
      const today = localDate(new Date());
      const items = list(d.items)
        .filter((i) => isText(i.title) && isText(i.fire_at))
        .filter((i) => briefing === "none" || (i.fire_at as string).slice(0, 10) === today) // the day at a glance: today only
        .map((i) => ({ title: i.title as string, kind: isText(i.kind) ? i.kind : "reminder", fire_at: i.fire_at as string }));
      return items.length > 0 ? [{ kind: "scheduled", items }] : [];
    }
    default:
      return [];
  }
}

/**
 * The cards for the results of one turn. A briefing gives what the user chose (weather, to-dos,
 * mail, news) and today's schedule if they want it; its question comes last.
 */
export function cardsFor(results: ActionResult[]): Card[] {
  const b = results.find((r) => r.tool === "daily_briefing" && r.data);
  const briefing = b ? (briefingParts(b.data as Data) ?? ["schedule"]) : "none";
  const cards = results
    .filter((r) => !(r.tool === "list_reminders" && briefing !== "none" && !briefing.includes("schedule")))
    .flatMap((r) => cardsOf(r, briefing));
  return [...cards.filter((c) => c.kind !== "briefing_choice"), ...cards.filter((c) => c.kind === "briefing_choice")];
}

/** "Өнөөдөр 18:00", "Маргааш", "10 сарын 15 09:30": short, for a card. The ISO time is read as written. */
export function shortWhen(iso: string, now = new Date()): string {
  const day = iso.slice(0, 10);
  const time = iso.slice(11, 16);
  const today = localDate(now);
  const tomorrow = localDate(new Date(now.getTime() + 86_400_000));
  const yesterday = localDate(new Date(now.getTime() - 86_400_000));
  const [, month, date] = day.split("-").map(Number);
  const dayWord =
    day === today ? "Өнөөдөр" : day === tomorrow ? "Маргааш" : day === yesterday ? "Өчигдөр" : `${month} сарын ${date}`;
  return time && time !== "23:59" ? `${dayWord} ${time}` : dayWord;
}

/** Past its time (or its day, for one due by the end of a day). */
export function isOverdue(iso: string, now = new Date()): boolean {
  return iso.slice(11, 16) === "23:59" ? iso.slice(0, 10) < localDate(now) : Date.parse(iso) < now.getTime();
}
