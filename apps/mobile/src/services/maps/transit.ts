import type { Ionicons } from "@expo/vector-icons";
import type {
  DirectionsResponse,
  LatLng,
  NearbyStop,
  TransitDetails,
  TransitVehicle,
} from "@bekhi/contracts";
import { colors } from "@/theme";
import { distanceM } from "./geo";

export const VEHICLE_ICONS: Record<
  TransitVehicle,
  keyof typeof Ionicons.glyphMap
> = {
  bus: "bus",
  trolleybus: "bus",
  tram: "train",
  train: "train",
  other: "bus",
};

export const NEARBY_STOP_COLOR = "#26C6DA";

/** Walking pace for a distance Google did not time, with streets not running straight. */
const WALK_MPS = 1.25;
const DETOUR = 1.3;
/** Less slack than this before the bus leaves: hurry. */
const HURRY_S = 120;
/** Closer than this, the rider is at the stop. */
const AT_STOP_M = 30;

/** The lines ridden, in order. */
export function rides(route: DirectionsResponse): TransitDetails[] {
  return route.steps.flatMap((s) => (s.transit ? [s.transit] : []));
}

export function lineColors(t: TransitDetails): {
  background: string;
  text: string;
} {
  return {
    background: t.color ?? colors.accent,
    text: t.text_color ?? colors.background,
  };
}

export type StopMarker = {
  key: string;
  coordinate: LatLng;
  title: string;
  description: string;
  color: string;
};

/** Where to get on and off each line, for the map. */
export function stopMarkers(route: DirectionsResponse): StopMarker[] {
  return rides(route).flatMap((t, i) => {
    const color = lineColors(t).background;
    const marks: StopMarker[] = [];
    if (t.departure_stop.location) {
      marks.push({
        key: `${i}-on`,
        coordinate: t.departure_stop.location,
        title: t.departure_stop.name,
        description: `${t.line} суух`,
        color,
      });
    }
    if (t.arrival_stop.location) {
      marks.push({
        key: `${i}-off`,
        coordinate: t.arrival_stop.location,
        title: t.arrival_stop.name,
        description: `${t.line} буух`,
        color,
      });
    }
    return marks;
  });
}

/** "14:05" on the phone's clock. */
export function clock(at: Date): string {
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
}

export function walkSeconds(metres: number): number {
  return Math.round((metres * DETOUR) / WALK_MPS);
}

/**
 * Both sides of a street are separate stops with one name: the list keeps the nearest of
 * each name, the map shows them all.
 */
export function uniqueByName(stops: NearbyStop[]): NearbyStop[] {
  const seen = new Set<string>();
  return stops.filter((s) => !seen.has(s.name) && !!seen.add(s.name));
}

export type BusCatch = {
  /** relaxed: time to spare; hurry: leave now; at_stop: wait there; missed: it has gone. */
  kind: "relaxed" | "hurry" | "at_stop" | "missed";
  transit: TransitDetails;
  departs: Date;
  /** Seconds until the rider should start walking (relaxed), or until the bus comes (at_stop). */
  seconds: number;
};

/**
 * Can the rider still catch the first bus of the route? Google's walk to the stop, scaled to
 * how far the rider is from it now, against the bus's timetabled departure.
 */
export function catchFirstBus(
  route: DirectionsResponse,
  here: LatLng | null,
  now: number,
): BusCatch | null {
  const first = route.steps.findIndex((s) => s.transit);
  const transit = route.steps[first]?.transit;
  if (!transit?.departure_time) return null;
  const departs = new Date(transit.departure_time);
  const untilBusS = (departs.getTime() - now) / 1000;

  const walkBefore = route.steps.slice(0, first);
  let walkS = walkBefore.reduce(
    (sum, s) => sum + (s.duration_s || walkSeconds(s.distance_m)),
    0,
  );
  const stop = transit.departure_stop.location;
  const start = route.path[0];
  if (here && stop) {
    const leftM = distanceM(here, stop);
    if (leftM < AT_STOP_M) {
      return untilBusS < -60
        ? { kind: "missed", transit, departs, seconds: 0 }
        : {
            kind: "at_stop",
            transit,
            departs,
            seconds: Math.max(0, Math.round(untilBusS)),
          };
    }
    const fromStartM = start ? distanceM(start, stop) : 0;
    walkS =
      fromStartM > AT_STOP_M && walkS > 0
        ? walkS * (leftM / fromStartM)
        : walkSeconds(leftM);
  }

  const spareS = Math.round(untilBusS - walkS);
  if (spareS < 0) return { kind: "missed", transit, departs, seconds: 0 };
  if (spareS < HURRY_S) return { kind: "hurry", transit, departs, seconds: 0 };
  return { kind: "relaxed", transit, departs, seconds: spareS };
}
