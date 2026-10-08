/**
 * Finds the contact the user named when the two are written differently. Speech recognition
 * gives Cyrillic ("Анка", "Хулан"), while contacts are often saved in Latin letters ("Anka",
 * "Khulan") or as a family word ("Mom"). Both sides are reduced to the same rough Latin key that
 * ignores the usual spelling variants: х = h/kh/x, ө/ү = o/u, ц = ts/c, й/ы = i/y, doubled letters.
 */

const CYRILLIC: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "j", з: "z", и: "i", й: "i", к: "k",
  л: "l", м: "m", н: "n", о: "o", ө: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ү: "u", ф: "f",
  х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sh", ъ: "", ы: "i", ь: "", э: "e", ю: "yu", я: "ya",
};

/** Family words people save contacts under instead of a name. */
const FAMILY: Record<string, string[]> = {
  ээж: ["mom", "mommy", "mum", "mama", "mother", "eej", "eejee"],
  аав: ["dad", "daddy", "papa", "father", "aav", "aavaa"],
  эмээ: ["grandma", "grandmother", "granny", "emee"],
  өвөө: ["grandpa", "grandfather", "uvuu", "ovoo"],
};

function tokenKey(token: string): string {
  return [...token.toLocaleLowerCase()]
    .map((c) => CYRILLIC[c] ?? c)
    .join("")
    .normalize("NFD")
    .replace(/\p{M}/gu, "") // ö → o, ü → u
    .replace(/zh/g, "j")
    .replace(/kh|x/g, "h")
    .replace(/ts/g, "c")
    .replace(/y/g, "i")
    .replace(/o/g, "u")
    .replace(/w/g, "v")
    .replace(/[^a-z]/g, "")
    .replace(/(.)\1+/g, "$1");
}

/** The name as rough Latin keys, one per word ("Бат-Эрдэнэ" → ["bat", "erdene"]). */
export function nameKeys(name: string): string[] {
  return name
    .split(/[\s\-_.,]+/)
    .map(tokenKey)
    .filter(Boolean);
}

export const sameName = (a: string, b: string) => nameKeys(a).join(" ") === nameKeys(b).join(" ");

/**
 * The contacts whose name matches what the user said: whole name or one of its words with the
 * same key first; otherwise words that start with it ("Бат" → "Batbold"), like the system search.
 */
export function matchContacts<T extends { fullName?: string | null }>(contacts: readonly T[], spoken: string): T[] {
  const said = nameKeys(spoken);
  if (said.length === 0) return [];
  const whole = said.join(" ");
  const family = (FAMILY[spoken.trim().toLocaleLowerCase()] ?? []).map((w) => nameKeys(w).join(" "));
  const wanted = new Set([whole, said.join(""), ...family]);

  const exact = contacts.filter((c) => {
    const keys = nameKeys(c.fullName ?? "");
    return wanted.has(keys.join(" ")) || wanted.has(keys.join("")) || (said.length === 1 && keys.some((k) => wanted.has(k)));
  });
  if (exact.length > 0) return exact;

  const first = said[0] ?? "";
  if (said.length > 1 || first.length < 3) return [];
  return contacts.filter((c) => nameKeys(c.fullName ?? "").some((k) => k.startsWith(first)));
}
