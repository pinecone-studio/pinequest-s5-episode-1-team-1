import type { ActionResult } from "@bekhi/contracts";
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
  | { kind: "scheduled"; items: { title: string; kind: string; fire_at: string }[] };

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

function cardsOf(r: ActionResult, briefing: boolean): Card[] {
  const d = r.data;
  if (r.status !== "succeeded" || !d) return [];
  switch (r.tool) {
    case "list_todos":
      return [todos(d.items)].filter((c): c is Card => c !== null);
    case "get_weather":
      return [weather(d)].filter((c): c is Card => c !== null);
    case "daily_briefing": {
      const w = typeof d.weather === "object" && d.weather !== null ? weather(d.weather as Data) : null;
      return [w, todos(d.todos)].filter((c): c is Card => c !== null);
    }
    case "check_email": {
      const emails = list(d.emails)
        .filter((e) => isText(e.from) || isText(e.subject))
        .map((e) => ({
          from: isText(e.from) ? e.from : "",
          subject: isText(e.subject) ? e.subject : "",
          snippet: isText(e.snippet) ? e.snippet : "",
          unread: e.unread === true,
        }));
      return emails.length > 0 ? [{ kind: "emails", emails }] : [];
    }
    case "read_email":
      return isText(d.text) && d.text.trim()
        ? [{ kind: "email", subject: isText(d.subject) ? d.subject : "", from: isText(d.from) ? d.from : "", text: d.text }]
        : [];
    case "list_reminders": {
      const today = localDate(new Date());
      const items = list(d.items)
        .filter((i) => isText(i.title) && isText(i.fire_at))
        .filter((i) => !briefing || (i.fire_at as string).slice(0, 10) === today) // the day at a glance: today only
        .map((i) => ({ title: i.title as string, kind: isText(i.kind) ? i.kind : "reminder", fire_at: i.fire_at as string }));
      return items.length > 0 ? [{ kind: "scheduled", items }] : [];
    }
    default:
      return [];
  }
}

/** The cards for the results of one turn (a briefing gives the weather, the to-dos and today's schedule). */
export function cardsFor(results: ActionResult[]): Card[] {
  const briefing = results.some((r) => r.tool === "daily_briefing");
  return results.flatMap((r) => cardsOf(r, briefing));
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
