import { useEffect, useMemo, useRef } from "react";
import { Platform, StyleSheet } from "react-native";
import { isRunningInExpoGo } from "expo";
import Constants from "expo-constants";
import MapView, { Marker, Polyline, PROVIDER_GOOGLE } from "react-native-maps";
import type {
  DirectionsResponse,
  LatLng,
  NearbyStop,
} from "@bekhi/contracts";
import { NEARBY_STOP_COLOR, stopMarkers } from "@/services/maps/transit";
import { colors } from "@/theme";

export type RouteMapProps = {
  location: LatLng | null;
  route: DirectionsResponse | null;
  /** Bus stops around the user, shown while there is no route. */
  stops: NearbyStop[];
  /** Moves the map here when it changes, e.g. a stop picked from the list. */
  focus: LatLng | null;
  /** Room taken by overlays (search bar, route card), so the route is fitted between them. */
  inset: { top: number; bottom: number };
};

const ULAANBAATAR = { latitude: 47.9185, longitude: 106.9177 };

/**
 * Google Maps on Android. On iPhone too in a build made with GOOGLE_MAPS_IOS_API_KEY
 * (app.config.ts); otherwise, and in Expo Go, iOS draws the route on Apple Maps.
 */
const provider =
  Platform.OS === "android" ||
  (!isRunningInExpoGo() &&
    Constants.expoConfig?.extra?.googleMapsOnIos === true)
    ? PROVIDER_GOOGLE
    : undefined;

export function RouteMap({
  location,
  route,
  stops,
  focus,
  inset,
}: RouteMapProps) {
  const map = useRef<MapView>(null);
  const centered = useRef(false);
  const rideStops = useMemo(() => (route ? stopMarkers(route) : []), [route]);

  useEffect(() => {
    if (!route) return;
    map.current?.fitToCoordinates(
      location ? [location, ...route.path] : route.path,
      {
        edgePadding: {
          top: inset.top + 24,
          right: 40,
          bottom: inset.bottom + 24,
          left: 40,
        },
        animated: true,
      },
    );
    // Fitted once per route, not on every position update; the map's own button follows the user.
  }, [route]);

  useEffect(() => {
    if (!location || route || centered.current) return;
    centered.current = true;
    map.current?.animateCamera(
      { center: location, zoom: 16 },
      { duration: 600 },
    );
  }, [location, route]);

  useEffect(() => {
    if (focus)
      map.current?.animateCamera(
        { center: focus, zoom: 17 },
        { duration: 500 },
      );
  }, [focus]);

  return (
    <MapView
      ref={map}
      style={StyleSheet.absoluteFill}
      provider={provider}
      initialRegion={{
        ...ULAANBAATAR,
        latitudeDelta: 0.08,
        longitudeDelta: 0.08,
      }}
      showsUserLocation
      showsMyLocationButton
      toolbarEnabled={false}
      userInterfaceStyle="dark"
      mapPadding={{ top: inset.top, right: 0, bottom: inset.bottom, left: 0 }}
    >
      {route && (
        <Polyline
          coordinates={route.path}
          strokeWidth={6}
          strokeColor={colors.accent}
        />
      )}
      {route && <Marker coordinate={route.destination} />}
      {rideStops.map((s) => (
        <Marker
          key={s.key}
          coordinate={s.coordinate}
          title={s.title}
          description={s.description}
          pinColor={s.color}
        />
      ))}
      {!route &&
        stops.map((s) => (
          <Marker
            key={s.id}
            coordinate={s.location}
            title={s.name}
            description="Автобусны буудал"
            pinColor={NEARBY_STOP_COLOR}
          />
        ))}
    </MapView>
  );
}
