import type { ToolArguments } from "@duud/contracts";

const TRAVEL_MODE = { driving: "driving", walking: "walking", transit: "transit" } as const;

/** Directions in Google Maps: opens the Maps app on Android, the website on a computer. */
export function googleMapsUrl(args: ToolArguments<"open_maps">): string {
  return (
    `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(args.destination)}` +
    `&travelmode=${TRAVEL_MODE[args.mode]}`
  );
}
