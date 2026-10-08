import { router } from "expo-router";
import type { ToolArguments } from "@bekhi/contracts";
import type { ActionOutcome } from "./IOSActionService";

const TRAVEL_MODE = { driving: "driving", walking: "walking", transit: "transit" } as const;

/**
 * Directions in Google Maps: opens the Maps app on Android, the website on a computer.
 * `navigate` starts turn-by-turn guidance from the current location straight away.
 */
export function googleMapsUrl(args: ToolArguments<"open_maps">, { navigate = false } = {}): string {
  return (
    `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(args.destination)}` +
    `&travelmode=${TRAVEL_MODE[args.mode]}` +
    (navigate ? "&dir_action=navigate" : "")
  );
}

/** BEKHI's own map screen: live location and the route. The route is looked up there. */
export async function openInAppMap(args: ToolArguments<"open_maps">): Promise<ActionOutcome> {
  try {
    router.push({ pathname: "/map", params: { destination: args.destination, mode: args.mode } });
    return { status: "handed_off", executed_via: "react_native", error_code: null };
  } catch {
    return { status: "failed", executed_via: "react_native", error_code: "MAP_SCREEN_FAILED" };
  }
}
