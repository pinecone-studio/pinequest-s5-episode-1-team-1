import { useEffect, useState } from "react";
import * as Location from "expo-location";
import type { LatLng } from "@bekhi/contracts";

export type LocationStatus = "waiting" | "live" | "denied" | "unavailable";

/** The phone's position while the screen is open: every ~10 m or 3 s, whichever is later. */
export function useLiveLocation(): { location: LatLng | null; status: LocationStatus } {
  const [location, setLocation] = useState<LatLng | null>(null);
  const [status, setStatus] = useState<LocationStatus>("waiting");

  useEffect(() => {
    let subscription: Location.LocationSubscription | undefined;
    let cancelled = false;
    (async () => {
      const { granted } = await Location.requestForegroundPermissionsAsync();
      if (cancelled) return;
      if (!granted) return setStatus("denied");
      const watch = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, distanceInterval: 10, timeInterval: 3000 },
        ({ coords }) => {
          setLocation({ latitude: coords.latitude, longitude: coords.longitude });
          setStatus("live");
        },
        () => setStatus("unavailable"),
      );
      if (cancelled) watch.remove();
      else subscription = watch;
    })().catch((e: unknown) => {
      console.warn("location failed", e);
      if (!cancelled) setStatus("unavailable");
    });
    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, []);

  return { location, status };
}
