const BACK_VOWELS = new Set([..."аоуяёы"]);
const FRONT_VOWELS = new Set([..."эөүе"]);

/**
 * Directional case "руу/рүү/луу/лүү" by vowel harmony of the last word:
 * "Бат руу", "Ээж рүү", "Баатар луу", "Сүхбаатарын талбай руу".
 * Mirrors toward() in apps/api/src/bekhi_api/compose.py.
 */
export function toward(phrase: string): string {
  const word = (phrase.trim().split(/\s+/).pop() ?? "").toLowerCase();
  const chars = [...word];
  const back = chars.some((c) => BACK_VOWELS.has(c))
    ? true
    : chars.some((c) => FRONT_VOWELS.has(c) || c === "и")
      ? false
      : true;
  const stem = word.endsWith("р") ? "л" : "р";
  return `${phrase} ${stem}${back ? "уу" : "үү"}`;
}
