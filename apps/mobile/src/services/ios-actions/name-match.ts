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

/** Below this a contact is too far from the name to offer. */
const MIN_SCORE = 0.82;

/** How alike two keys are, 0 to 1 (Jaro-Winkler: forgives a misheard letter, trusts a shared start). */
function similarity(a: string, b: string): number {
  if (a === b) return 1;
  if (!a || !b) return 0;
  const range = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
  const aHit: boolean[] = [];
  const bHit: boolean[] = [];
  let matches = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = Math.max(0, i - range); j < Math.min(b.length, i + range + 1); j++) {
      if (bHit[j] || a[i] !== b[j]) continue;
      aHit[i] = bHit[j] = true;
      matches++;
      break;
    }
  }
  if (matches === 0) return 0;
  let k = 0;
  let swapped = 0;
  for (let i = 0; i < a.length; i++) {
    if (!aHit[i]) continue;
    while (!bHit[k]) k++;
    if (a[i] !== b[k]) swapped++;
    k++;
  }
  const jaro = (matches / a.length + matches / b.length + (matches - swapped / 2) / matches) / 3;
  let prefix = 0;
  while (prefix < 4 && a[prefix] !== undefined && a[prefix] === b[prefix]) prefix++;
  return jaro + prefix * 0.1 * (1 - jaro);
}

/**
 * Contacts ranked by how well their name matches any spoken form: the name as heard plus the
 * assistant's spellings of it ("Anka", "Michael"). 1 means the same name; misheard names still
 * rank close, so the user can pick the right one.
 */
export function rankContacts<T extends { fullName?: string | null }>(
  contacts: readonly T[],
  spoken: readonly string[],
): { contact: T; score: number }[] {
  const wanted = new Set<string>();
  for (const form of spoken) {
    const keys = nameKeys(form);
    if (keys.length === 0) continue;
    wanted.add(keys.join(" "));
    wanted.add(keys.join(""));
    for (const w of FAMILY[form.trim().toLocaleLowerCase()] ?? []) wanted.add(nameKeys(w).join(" "));
  }
  if (wanted.size === 0) return [];

  const ranked: { contact: T; score: number }[] = [];
  for (const contact of contacts) {
    const keys = nameKeys(contact.fullName ?? "");
    if (keys.length === 0) continue;
    let score = 0;
    for (const w of wanted) {
      score = Math.max(score, similarity(w, keys.join(" ")), similarity(w, keys.join("")));
      // One word of a longer name ("Khulan" in "Khulan Bat") ranks just below the whole name.
      for (const k of keys) score = Math.max(score, similarity(w, k) * 0.99);
    }
    if (score >= MIN_SCORE) ranked.push({ contact, score });
  }
  return ranked.sort((x, y) => y.score - x.score);
}
