import type { LatLng } from "@bekhi/contracts";

const EARTH_RADIUS_M = 6_371_000;
const METRES_PER_DEGREE = (EARTH_RADIUS_M * Math.PI) / 180;
const rad = (deg: number) => (deg * Math.PI) / 180;

/** Great-circle distance in metres. */
export function distanceM(a: LatLng, b: LatLng): number {
  const dLat = rad(b.latitude - a.latitude);
  const dLng = rad(b.longitude - a.longitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

export function pathLengthM(path: LatLng[]): number {
  let total = 0;
  for (let i = 1; i < path.length; i++) total += distanceM(path[i - 1]!, path[i]!);
  return total;
}

/**
 * Where `here` is along `path`: how far it is from the route, and how many metres of the
 * route are left after the closest point. Flat-earth projection: fine at city scale.
 */
export function progressAlong(path: LatLng[], here: LatLng): { offRouteM: number; remainingM: number } {
  if (path.length < 2) {
    const end = path[0];
    const d = end ? distanceM(here, end) : 0;
    return { offRouteM: d, remainingM: d };
  }
  const kx = Math.cos(rad(here.latitude)) * METRES_PER_DEGREE;
  const ky = METRES_PER_DEGREE;
  let best = { offRouteM: Infinity, segment: 0, t: 0 };
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i]!;
    const b = path[i + 1]!;
    const ax = (a.longitude - here.longitude) * kx;
    const ay = (a.latitude - here.latitude) * ky;
    const dx = (b.longitude - a.longitude) * kx;
    const dy = (b.latitude - a.latitude) * ky;
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2));
    const off = Math.hypot(ax + t * dx, ay + t * dy);
    if (off < best.offRouteM) best = { offRouteM: off, segment: i, t };
  }
  let remainingM = (1 - best.t) * distanceM(path[best.segment]!, path[best.segment + 1]!);
  for (let i = best.segment + 1; i < path.length - 1; i++) remainingM += distanceM(path[i]!, path[i + 1]!);
  return { offRouteM: best.offRouteM, remainingM };
}

export function formatDistance(m: number): string {
  return m < 1000 ? `${Math.max(0, Math.round(m / 10) * 10)} м` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} км`;
}

export function formatDuration(s: number): string {
  const minutes = Math.max(1, Math.round(s / 60));
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} цаг ${rest} мин` : `${hours} цаг`;
}
