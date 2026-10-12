import {
  DirectionsResponse,
  NearbyStopsResponse,
  type DirectionsRequest,
  type NearbyStopsRequest,
} from "@bekhi/contracts";
import { postMaps } from "./api";
import { distanceM } from "./geo";

export const NEARBY_RADIUS_M = 600;
/** The voice command and the map screen ask for the same stops a moment apart: one billed request. */
const STOPS_CACHE_MS = 60_000;
const STOPS_CACHE_M = 100;
let lastStops: {
  at: number;
  req: NearbyStopsRequest;
  res: NearbyStopsResponse;
} | null = null;

/** A route from the backend (Google Routes API). Throws an Error with a Mongolian message. */
export function fetchDirections(
  req: DirectionsRequest,
): Promise<DirectionsResponse> {
  return postMaps(
    "/api/v1/maps/directions",
    req,
    DirectionsResponse,
    "Уучлаарай, зам тооцоолоход алдаа гарлаа.",
  );
}

/** Bus stops around a point, nearest first (Google Places API). */
export async function fetchNearbyStops(
  req: NearbyStopsRequest,
): Promise<NearbyStopsResponse> {
  if (
    lastStops &&
    Date.now() - lastStops.at < STOPS_CACHE_MS &&
    lastStops.req.radius_m === req.radius_m &&
    distanceM(lastStops.req.origin, req.origin) < STOPS_CACHE_M
  )
    return lastStops.res;
  const res = await postMaps(
    "/api/v1/maps/stops/nearby",
    req,
    NearbyStopsResponse,
    "Уучлаарай, ойрын буудлуудыг олоход алдаа гарлаа.",
  );
  lastStops = { at: Date.now(), req, res };
  return res;
}
