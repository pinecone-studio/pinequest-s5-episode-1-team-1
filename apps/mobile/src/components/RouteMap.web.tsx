import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import type { LatLng } from "@bekhi/contracts";
import { colors } from "@/theme";
import type { RouteMapProps } from "./RouteMap";

const ULAANBAATAR = { latitude: 47.9185, longitude: 106.9177 };

/** Browser key for the Maps JavaScript API. Public by design: restrict it to your site's address. */
const WEB_KEY = process.env.EXPO_PUBLIC_GOOGLE_MAPS_WEB_API_KEY;

// The few parts of the Maps JavaScript API used here (no @types/google.maps dependency).
type GLatLng = { lat: number; lng: number };
type GMap = {
  setCenter(c: GLatLng): void;
  setZoom(z: number): void;
  fitBounds(b: GBounds, padding: { top: number; right: number; bottom: number; left: number }): void;
};
type GBounds = { extend(p: GLatLng): void };
type GOverlay = { setMap(m: GMap | null): void; setPosition?(p: GLatLng): void };
type GMaps = {
  Map: new (el: HTMLElement, opts: object) => GMap;
  Polyline: new (opts: object) => GOverlay;
  Marker: new (opts: object) => GOverlay & { setPosition(p: GLatLng): void };
  LatLngBounds: new () => GBounds;
  SymbolPath: { CIRCLE: number };
};

let loading: Promise<GMaps> | null = null;

function loadGoogleMaps(key: string): Promise<GMaps> {
  const w = window as unknown as { google?: { maps?: GMaps } };
  if (w.google?.maps?.Map) return Promise.resolve(w.google.maps);
  loading ??= new Promise<GMaps>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&language=mn&region=MN`;
    script.async = true;
    script.onload = () => (w.google?.maps ? resolve(w.google.maps) : reject(new Error("maps script loaded without google.maps")));
    script.onerror = () => {
      loading = null;
      reject(new Error("maps script failed"));
    };
    document.head.appendChild(script);
  });
  return loading;
}

const toG = (p: LatLng): GLatLng => ({ lat: p.latitude, lng: p.longitude });

/** The same map in the browser, drawn with the Maps JavaScript API. */
export function RouteMap({ location, route, inset }: RouteMapProps) {
  const element = useRef<HTMLDivElement>(null);
  const [maps, setMaps] = useState<{ api: GMaps; map: GMap } | null>(null);
  const [failed, setFailed] = useState(false);
  const me = useRef<(GOverlay & { setPosition(p: GLatLng): void }) | null>(null);
  const centered = useRef(false);

  useEffect(() => {
    if (!WEB_KEY || !element.current) return;
    let cancelled = false;
    loadGoogleMaps(WEB_KEY)
      .then((api) => {
        if (cancelled || !element.current) return;
        const map = new api.Map(element.current, {
          center: toG(ULAANBAATAR),
          zoom: 12,
          disableDefaultUI: true,
          zoomControl: true,
          colorScheme: "DARK",
        });
        setMaps({ api, map });
      })
      .catch((e: unknown) => {
        console.warn("google maps failed to load", e);
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!maps || !location) return;
    if (me.current) me.current.setPosition(toG(location));
    else
      me.current = new maps.api.Marker({
        map: maps.map,
        position: toG(location),
        icon: { path: maps.api.SymbolPath.CIRCLE, scale: 8, fillColor: "#3D7BFF", fillOpacity: 1, strokeColor: "#FFFFFF", strokeWeight: 2 },
      });
    if (!route && !centered.current) {
      centered.current = true;
      maps.map.setCenter(toG(location));
      maps.map.setZoom(15);
    }
  }, [maps, location, route]);

  useEffect(() => {
    if (!maps || !route) return;
    const line = new maps.api.Polyline({ map: maps.map, path: route.path.map(toG), strokeColor: colors.accent, strokeWeight: 6 });
    const end = new maps.api.Marker({ map: maps.map, position: toG(route.destination) });
    const bounds = new maps.api.LatLngBounds();
    route.path.forEach((p) => bounds.extend(toG(p)));
    if (location) bounds.extend(toG(location));
    maps.map.fitBounds(bounds, { top: inset.top + 24, right: 40, bottom: inset.bottom + 24, left: 40 });
    return () => {
      line.setMap(null);
      end.setMap(null);
    };
    // Fitted once per route, not on every position update.
  }, [maps, route]);

  if (!WEB_KEY || failed) {
    return (
      <View style={[StyleSheet.absoluteFill, styles.placeholder]}>
        <Text style={styles.placeholderText}>
          {WEB_KEY
            ? "Google Maps ачаалж чадсангүй."
            : "Browser дээр газрын зураг харуулахын тулд apps/mobile/.env-д EXPO_PUBLIC_GOOGLE_MAPS_WEB_API_KEY тохируулна уу."}
        </Text>
      </View>
    );
  }
  return <div ref={element} style={{ position: "absolute", inset: 0 }} />;
}

const styles = StyleSheet.create({
  placeholder: { alignItems: "center", justifyContent: "center", padding: 32, paddingTop: 160, backgroundColor: colors.backgroundBottom },
  placeholderText: { maxWidth: 420, fontSize: 14, lineHeight: 20, textAlign: "center", color: colors.secondaryLabel },
});
