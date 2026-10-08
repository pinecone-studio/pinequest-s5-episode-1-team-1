import { useEffect, useRef } from "react";
import { Platform, StyleSheet } from "react-native";
import { isRunningInExpoGo } from "expo";
import Constants from "expo-constants";
import MapView, { Marker, Polyline, PROVIDER_GOOGLE } from "react-native-maps";
import type { DirectionsResponse, LatLng } from "@bekhi/contracts";
import { colors } from "@/theme";

export type RouteMapProps = {
  location: LatLng | null;
  route: DirectionsResponse | null;
  /** Room taken by overlays (search bar, route card), so the route is fitted between them. */
  inset: { top: number; bottom: number };
};

const ULAANBAATAR = { latitude: 47.9185, longitude: 106.9177 };

/**
 * Google Maps on Android. On iPhone too in a build made with GOOGLE_MAPS_IOS_API_KEY
 * (app.config.ts); otherwise, and in Expo Go, iOS draws the route on Apple Maps.
 */
const provider =
  Platform.OS === "android" || (!isRunningInExpoGo() && Constants.expoConfig?.extra?.googleMapsOnIos === true)
    ? PROVIDER_GOOGLE
    : undefined;

export function RouteMap({ location, route, inset }: RouteMapProps) {
  const map = useRef<MapView>(null);
  const centered = useRef(false);

  useEffect(() => {
    if (!route) return;
    map.current?.fitToCoordinates(location ? [location, ...route.path] : route.path, {
      edgePadding: { top: inset.top + 24, right: 40, bottom: inset.bottom + 24, left: 40 },
      animated: true,
    });
    // Fitted once per route, not on every position update; the map's own button follows the user.
  }, [route]);

  useEffect(() => {
    if (!location || route || centered.current) return;
    centered.current = true;
    map.current?.animateCamera({ center: location, zoom: 15 }, { duration: 600 });
  }, [location, route]);

  return (
    <MapView
      ref={map}
      style={StyleSheet.absoluteFill}
      provider={provider}
      initialRegion={{ ...ULAANBAATAR, latitudeDelta: 0.08, longitudeDelta: 0.08 }}
      showsUserLocation
      showsMyLocationButton
      toolbarEnabled={false}
      userInterfaceStyle="dark"
      mapPadding={{ top: inset.top, right: 0, bottom: inset.bottom, left: 0 }}
    >
      {route && <Polyline coordinates={route.path} strokeWidth={6} strokeColor={colors.accent} />}
      {route && <Marker coordinate={route.destination} />}
    </MapView>
  );
}
