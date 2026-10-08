import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Keyboard,
  type LayoutChangeEvent,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { TravelMode, type DirectionsResponse, type LatLng } from "@bekhi/contracts";
import { RouteMap } from "@/components/RouteMap";
import { tap } from "@/lib/haptics";
import { googleMapsUrl } from "@/services/ios-actions/maps";
import { fetchDirections } from "@/services/maps/directions";
import { distanceM, formatDistance, formatDuration, pathLengthM, progressAlong } from "@/services/maps/geo";
import { useLiveLocation } from "@/services/maps/useLiveLocation";
import { colors, MAX_CONTENT_WIDTH, radius } from "@/theme";

/** Further than this from the route, it is looked up again from where the user is now. */
const OFF_ROUTE_M = 60;
/** Each lookup is a billed Routes API request. */
const REROUTE_EVERY_MS = 20_000;
const ARRIVED_M = 30;

const MODES: { mode: TravelMode; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { mode: "driving", label: "Машин", icon: "car" },
  { mode: "walking", label: "Явган", icon: "walk" },
  { mode: "transit", label: "Нийтийн тээвэр", icon: "bus" },
];

type Target = { destination: string; mode: TravelMode };

export default function MapScreen() {
  const params = useLocalSearchParams<{ destination?: string; mode?: string }>();
  const paramMode = TravelMode.safeParse(params.mode);
  const { location, status } = useLiveLocation();
  const safe = useSafeAreaInsets();

  const [query, setQuery] = useState(params.destination ?? "");
  const [mode, setMode] = useState<TravelMode>(paramMode.success ? paramMode.data : "driving");
  const [target, setTarget] = useState<Target | null>(
    params.destination ? { destination: params.destination, mode: paramMode.success ? paramMode.data : "driving" } : null,
  );
  const [route, setRoute] = useState<DirectionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overlays, setOverlays] = useState({ top: 0, bottom: 0 });

  const request = useRef(0);
  const lastLookup = useRef(0);
  const locationRef = useRef(location);
  locationRef.current = location;

  const lookUp = useCallback(async (to: Target, from: LatLng, reroute: boolean) => {
    const id = ++request.current;
    lastLookup.current = Date.now();
    if (!reroute) {
      setLoading(true);
      setError(null);
      setRoute(null);
    }
    try {
      const found = await fetchDirections({ origin: from, destination: to.destination, mode: to.mode });
      if (id === request.current) {
        setRoute(found);
        setError(null);
      }
    } catch (e) {
      // A failed re-route keeps the route on screen.
      if (id === request.current && !reroute) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === request.current) setLoading(false);
    }
  }, []);

  // A new destination or mode: look it up as soon as the position is known.
  const hasFix = location !== null;
  useEffect(() => {
    if (target && locationRef.current) void lookUp(target, locationRef.current, false);
  }, [target, hasFix, lookUp]);

  const totalM = useMemo(() => (route ? pathLengthM(route.path) : 0), [route]);
  const progress = useMemo(() => (route && location ? progressAlong(route.path, location) : null), [route, location]);
  const arrived = route !== null && location !== null && distanceM(location, route.destination) < ARRIVED_M;

  useEffect(() => {
    if (!target || !location || !progress || loading || arrived) return;
    if (progress.offRouteM > OFF_ROUTE_M && Date.now() - lastLookup.current > REROUTE_EVERY_MS) {
      void lookUp(target, location, true);
    }
  }, [progress, target, location, loading, arrived, lookUp]);

  function search() {
    const destination = query.trim();
    if (!destination) return;
    Keyboard.dismiss();
    tap();
    setTarget({ destination, mode });
  }

  function chooseMode(next: TravelMode) {
    tap();
    setMode(next);
    if (target) setTarget({ ...target, mode: next });
  }

  function measured(edge: "top" | "bottom", e: LayoutChangeEvent) {
    // Read now: React Native reuses the event object once this handler returns.
    const height = Math.round(e.nativeEvent.layout.height);
    setOverlays((o) => (o[edge] === height ? o : { ...o, [edge]: height }));
  }

  function back() {
    if (router.canGoBack()) router.back();
    else router.replace("/");
  }

  function startNavigation() {
    if (!target) return;
    tap();
    void Linking.openURL(googleMapsUrl(target, { navigate: true }));
  }

  // Share of the route still ahead, for the time and distance left.
  const left = route ? (progress && totalM > 0 ? Math.min(1, progress.remainingM / totalM) : 1) : 0;
  const secondsLeft = route ? Math.round(route.duration_s * left) : 0;

  return (
    <View style={styles.screen}>
      <RouteMap
        location={location}
        route={route}
        inset={{ top: safe.top + overlays.top, bottom: safe.bottom + overlays.bottom }}
      />

      <SafeAreaView style={styles.overlay} edges={["top", "bottom"]}>
        <View style={styles.column} onLayout={(e) => measured("top", e)}>
          <View style={styles.searchRow}>
            <Pressable accessibilityRole="button" accessibilityLabel="Буцах" onPress={back} hitSlop={8} style={styles.iconButton}>
              <Ionicons name="chevron-back" size={22} color={colors.label} />
            </Pressable>
            <View style={styles.search}>
              <Ionicons name="search" size={18} color={colors.secondaryLabel} />
              <TextInput
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={search}
                placeholder="Хаашаа явах вэ?"
                placeholderTextColor={colors.tertiaryLabel}
                returnKeyType="search"
                autoCorrect={false}
                style={styles.input}
              />
              {query.length > 0 && (
                <Pressable accessibilityRole="button" accessibilityLabel="Зам хайх" onPress={search} hitSlop={8}>
                  <Ionicons name="arrow-forward-circle" size={26} color={colors.accent} />
                </Pressable>
              )}
            </View>
          </View>
          <View style={styles.modes}>
            {MODES.map((m) => (
              <Pressable
                key={m.mode}
                accessibilityRole="button"
                accessibilityState={{ selected: mode === m.mode }}
                onPress={() => chooseMode(m.mode)}
                style={[styles.mode, mode === m.mode && styles.modeSelected]}
              >
                <Ionicons name={m.icon} size={16} color={mode === m.mode ? colors.background : colors.label} />
                <Text style={[styles.modeText, mode === m.mode && styles.modeTextSelected]}>{m.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={styles.column} onLayout={(e) => measured("bottom", e)}>
          <View style={styles.card}>
            {status === "denied" ? (
              <View style={styles.message}>
                <Text style={styles.messageText}>
                  Зам заахын тулд байршлын зөвшөөрөл хэрэгтэй. Утасны тохиргооноос BEKHI-д байршил зөвшөөрнө үү.
                </Text>
                {Platform.OS !== "web" && (
                  <Pressable onPress={() => void Linking.openSettings()} style={styles.secondaryButton}>
                    <Text style={styles.secondaryButtonText}>Тохиргоо нээх</Text>
                  </Pressable>
                )}
              </View>
            ) : status === "unavailable" ? (
              <Text style={styles.messageText}>Байршлыг тодорхойлж чадсангүй. GPS асаалттай эсэхийг шалгана уу.</Text>
            ) : !location ? (
              <View style={styles.row}>
                <ActivityIndicator color={colors.secondaryLabel} />
                <Text style={styles.messageText}>Байршлыг тодорхойлж байна…</Text>
              </View>
            ) : loading ? (
              <View style={styles.row}>
                <ActivityIndicator color={colors.secondaryLabel} />
                <Text style={styles.messageText}>Зам тооцоолж байна…</Text>
              </View>
            ) : error ? (
              <Text style={styles.errorText}>{error}</Text>
            ) : route && target ? (
              <>
                {arrived ? (
                  <Text style={styles.eta}>Хүрлээ 🎉</Text>
                ) : (
                  <View style={styles.summary}>
                    <Text style={styles.eta}>{formatDuration(secondsLeft)}</Text>
                    <Text style={styles.summaryText}>
                      {formatDistance(route.distance_m * left)} · {arrivalTime(secondsLeft)}-д хүрнэ
                    </Text>
                  </View>
                )}
                <Text style={styles.destination} numberOfLines={1}>
                  {target.destination}
                </Text>
                {route.steps.length > 0 && !arrived && (
                  <ScrollView style={styles.steps} showsVerticalScrollIndicator={false}>
                    {route.steps.map((s, i) => (
                      <View key={i} style={styles.step}>
                        <Text style={styles.stepText}>{s.instruction}</Text>
                        {s.distance_m > 0 && <Text style={styles.stepDistance}>{formatDistance(s.distance_m)}</Text>}
                      </View>
                    ))}
                  </ScrollView>
                )}
                <Pressable onPress={startNavigation} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
                  <Ionicons name="navigate" size={18} color={colors.background} />
                  <Text style={styles.primaryButtonText}>Google Maps-ээр хөтлүүлэх</Text>
                </Pressable>
              </>
            ) : (
              <Text style={styles.messageText}>Очих газраа бичээд хайна уу. Жишээ нь: Сансар, Зайсан, Улсын их дэлгүүр.</Text>
            )}
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

function arrivalTime(secondsFromNow: number): string {
  const at = new Date(Date.now() + secondsFromNow * 1000);
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
}

const glass = {
  backgroundColor: "rgba(21,22,29,0.92)",
  borderWidth: StyleSheet.hairlineWidth,
  borderColor: colors.border,
} as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  overlay: { ...StyleSheet.absoluteFill, justifyContent: "space-between", pointerEvents: "box-none" },
  column: { width: "100%", maxWidth: MAX_CONTENT_WIDTH, alignSelf: "center", paddingHorizontal: 14, paddingVertical: 8, gap: 8, pointerEvents: "box-none" },
  searchRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  iconButton: { ...glass, width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  search: { ...glass, flex: 1, height: 44, borderRadius: 22, flexDirection: "row", alignItems: "center", gap: 8, paddingLeft: 14, paddingRight: 8 },
  input: { flex: 1, height: 44, fontSize: 16, color: colors.label },
  modes: { flexDirection: "row", gap: 8, pointerEvents: "box-none" },
  mode: { ...glass, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.chip },
  modeSelected: { backgroundColor: colors.label, borderColor: colors.label },
  modeText: { fontSize: 13, fontWeight: "600", color: colors.label },
  modeTextSelected: { color: colors.background },
  card: { ...glass, borderRadius: radius.sheet, padding: 18, gap: 10 },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  message: { gap: 12 },
  messageText: { flexShrink: 1, fontSize: 15, lineHeight: 21, color: colors.secondaryLabel },
  errorText: { fontSize: 15, lineHeight: 21, color: colors.warning },
  summary: { gap: 2 },
  eta: { fontSize: 30, fontWeight: "800", color: colors.success, letterSpacing: -0.5 },
  summaryText: { fontSize: 15, color: colors.secondaryLabel },
  destination: { fontSize: 17, fontWeight: "600", color: colors.label },
  steps: { maxHeight: 150 },
  step: { flexDirection: "row", justifyContent: "space-between", gap: 12, paddingVertical: 7, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  stepText: { flex: 1, fontSize: 14, lineHeight: 19, color: colors.label },
  stepDistance: { fontSize: 13, color: colors.tertiaryLabel },
  primaryButton: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 48, borderRadius: 24, backgroundColor: colors.accent },
  primaryButtonText: { fontSize: 16, fontWeight: "700", color: colors.background },
  pressed: { opacity: 0.8 },
  secondaryButton: { alignSelf: "flex-start", paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.chip, backgroundColor: colors.surface },
  secondaryButtonText: { fontSize: 14, fontWeight: "600", color: colors.label },
});
