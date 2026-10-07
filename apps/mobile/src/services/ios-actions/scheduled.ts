import type { ToolArguments } from "@duud/contracts";

/** A reminder, alarm, event reminder or timer Duud scheduled on this device. */
export interface ScheduledItem {
  id: string;
  title: string;
  kind: string;
  /** Local wall-clock ISO with offset. */
  fire_at: string;
}

/** Minutes either side of a spoken time ("3 цагийнхаа сануулга") that still count as that item. */
const MATCH_WINDOW_MS = 15 * 60_000;

const normalize = (s: string) => s.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");

/**
 * The items cancel_reminder means, and whether the request is ambiguous (several, no filter).
 * Same rules as the computer's (apps/api desktop.py pick_scheduled).
 */
export function pickScheduled(
  items: ScheduledItem[],
  args: ToolArguments<"cancel_reminder">,
): { matches: ScheduledItem[]; ambiguous: boolean } {
  if (args.all) return { matches: items, ambiguous: false };
  const query = normalize(args.query ?? "");
  const at = args.at ? Date.parse(args.at) : null;
  if (!query && at === null) return { matches: items, ambiguous: items.length > 1 };
  const matches = items.filter(
    (i) =>
      (!query || normalize(i.title).includes(query)) && (at === null || Math.abs(Date.parse(i.fire_at) - at) <= MATCH_WINDOW_MS),
  );
  return { matches, ambiguous: false };
}
