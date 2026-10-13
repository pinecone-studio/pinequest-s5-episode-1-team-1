import { router } from "expo-router";
import * as Location from "expo-location";
import type { LatLng, ToolArguments } from "@bekhi/contracts";
import { fetchNearbyStops, fetchRestaurants, NEARBY_RADIUS_M } from "@/services/maps/directions";
import { uniqueByName } from "@/services/maps/transit";
import type { ActionOutcome } from "./IOSActionService";

/** Stops read out by voice; the map shows them all. */
const SPOKEN_STOPS = 3;
/** Places to eat within a 15-20 minute walk. */
const FOOD_RADIUS_M = 1500;
/** Places to eat shown on the card (the first few are read out). */
const LISTED_PLACES = 6;

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

/**
 * The nearest bus stops: looked up from the phone's position, shown on BEKHI's map, and
 * returned by name and distance for the spoken answer. The position itself is not returned.
 */
export async function findStopsOnMap(): Promise<ActionOutcome> {
  const origin = await currentPosition();
  if ("status" in origin) return origin;
  const found = await fetchNearbyStops({ origin, radius_m: NEARBY_RADIUS_M }).catch(() => null);
  if (!found) return fail("STOPS_FAILED");
  try {
    router.push("/map");
  } catch {
    return fail("MAP_SCREEN_FAILED");
  }
  const stops = uniqueByName(found.stops)
    .slice(0, SPOKEN_STOPS)
    .map(({ name, distance_m }) => ({ name, distance_m }));
  return { status: "succeeded", executed_via: "react_native", error_code: null, data: { stops } };
}

/**
 * Places to eat near the phone, for a dish or any: shown as a card in the chat (tap one for the
 * way there) and read out nearest first. The phone's own position is not returned.
 */
export async function findRestaurantsNearby(args: ToolArguments<"find_restaurants">): Promise<ActionOutcome> {
  const origin = await currentPosition();
  if ("status" in origin) return origin;
  const found = await fetchRestaurants({ origin, query: args.query, radius_m: FOOD_RADIUS_M }).catch(() => null);
  if (!found) return fail("RESTAURANTS_FAILED");
  const restaurants = found.restaurants
    .slice(0, LISTED_PLACES)
    .map(({ name, address, distance_m, rating, rating_count, open_now, kind }) => ({
      name,
      address,
      distance_m,
      rating,
      rating_count,
      open_now,
      kind,
    }));
  return {
    status: "succeeded",
    executed_via: "react_native",
    error_code: null,
    data: { query: args.query ?? null, restaurants },
  };
}

function fail(error_code: string): ActionOutcome {
  return { status: "failed", executed_via: "react_native", error_code };
}

/** The phone's position, or the outcome to report when it cannot be had. */
async function currentPosition(): Promise<LatLng | ActionOutcome> {
  const { granted } = await Location.requestForegroundPermissionsAsync().catch(() => ({ granted: false }));
  if (!granted) return { status: "permission_denied", executed_via: "react_native", error_code: "LOCATION_DENIED" };
  const here = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }).catch(() => null);
  if (!here) return fail("LOCATION_UNAVAILABLE");
  return { latitude: here.coords.latitude, longitude: here.coords.longitude };
}
