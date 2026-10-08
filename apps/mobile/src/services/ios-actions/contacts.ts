import { Contact, ContactField, requestPermissionsAsync } from "expo-contacts";
import { rankContacts } from "./name-match";

export type ContactLookup =
  | { kind: "found"; number: string }
  | { kind: "ambiguous"; count: number }
  | { kind: "not_found" }
  | { kind: "no_number" }
  | { kind: "permission_denied" };

/** A contact the phone found for the name the user said. Shown on screen, never sent anywhere. */
export interface ContactCandidate {
  name: string;
  number: string;
}

export type ContactSearch =
  | { kind: "candidates"; candidates: ContactCandidate[]; sure: boolean }
  | { kind: "not_found" }
  | { kind: "no_number" }
  | { kind: "permission_denied" };

const FIELDS = [ContactField.FULL_NAME, ContactField.PHONES] as const;
const MOBILE_LABEL = /mobile|iphone|cell|гар/i;
const MAX_CANDIDATES = 4;
/** Scores this high are the same name; a runner-up this close makes it a choice. */
const SAME_NAME = 0.97;
const CLOSE = 0.9;

/**
 * The contacts that may be the person the user named ("Анка", "Ээж"), best first. `sure` when
 * one stands out, so the app can just ask "Anka руу залгах уу?"; otherwise the user picks.
 * `spellings` are the assistant's guesses at how the name is saved ("Anka", "Mom").
 */
export async function findContacts(name: string, spellings: readonly string[] = []): Promise<ContactSearch> {
  const permission = await requestPermissionsAsync();
  if (!permission.granted) return { kind: "permission_denied" };

  const ranked = rankContacts(await Contact.getAllDetails(FIELDS), [name, ...spellings]);
  if (ranked.length === 0) return { kind: "not_found" };
  const reachable = ranked
    .map(({ contact, score }) => ({ name: contact.fullName ?? "", number: mobileNumber(contact.phones), score }))
    .filter((c): c is ContactCandidate & { score: number } => !!c.number)
    .slice(0, MAX_CANDIDATES);
  const [first, second] = reachable;
  if (!first) return { kind: "no_number" };
  const sure = !second || (first.score >= SAME_NAME && second.score < CLOSE);
  return { kind: "candidates", candidates: reachable.map(({ name: n, number }) => ({ name: n, number })), sure };
}

/** The phone number of the contact the user named, when the screen did not ask who it is. */
export async function lookupPhone(name: string, spellings: readonly string[] = []): Promise<ContactLookup> {
  const search = await findContacts(name, spellings);
  if (search.kind !== "candidates") return search;
  const [only] = search.candidates;
  if (!only) return { kind: "not_found" };
  return search.sure ? { kind: "found", number: only.number } : { kind: "ambiguous", count: search.candidates.length };
}

function mobileNumber(phones: readonly { number?: string | null; label?: string | null }[] | null | undefined): string | null {
  const numbered = (phones ?? []).filter((p) => p.number);
  return (numbered.find((p) => MOBILE_LABEL.test(p.label ?? "")) ?? numbered[0])?.number ?? null;
}
