import { Contact, ContactField, requestPermissionsAsync } from "expo-contacts";

export type ContactLookup =
  | { kind: "found"; number: string }
  | { kind: "ambiguous"; count: number }
  | { kind: "not_found" }
  | { kind: "no_number" }
  | { kind: "permission_denied" };

const FIELDS = [ContactField.FULL_NAME, ContactField.PHONES] as const;
const MOBILE_LABEL = /mobile|iphone|cell|гар/i;

const normalize = (s: string) => s.toLocaleLowerCase().replace(/\s+/g, " ").trim();

/**
 * The phone number of the contact the user named ("Ээж", "Бат"). Resolved on the phone;
 * names and numbers never leave it, only the outcome does.
 */
export async function lookupPhone(name: string): Promise<ContactLookup> {
  const permission = await requestPermissionsAsync();
  if (!permission.granted) return { kind: "permission_denied" };

  const matches = await Contact.getAllDetails(FIELDS, { name, limit: 20 });
  if (matches.length === 0) return { kind: "not_found" };
  const reachable = matches.filter((c) => c.phones?.some((p) => p.number));
  if (reachable.length === 0) return { kind: "no_number" };

  // "Бат" also matches "Батболд"; an exact name wins over partial matches.
  const exact = reachable.filter((c) => normalize(c.fullName ?? "") === normalize(name));
  const candidates = exact.length > 0 ? exact : reachable;
  const [only] = candidates;
  if (candidates.length > 1 || !only) return { kind: "ambiguous", count: candidates.length };

  const phones = (only.phones ?? []).filter((p) => p.number);
  const phone = phones.find((p) => MOBILE_LABEL.test(p.label ?? "")) ?? phones[0];
  return phone?.number ? { kind: "found", number: phone.number } : { kind: "no_number" };
}
