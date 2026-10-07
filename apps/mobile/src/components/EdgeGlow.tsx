import { useEffect, useRef } from "react";
import { Animated, Easing, Platform, StyleSheet } from "react-native";
import { glow } from "@/theme";

const NATIVE = Platform.OS !== "web";
const { orange, pink, purple, blue, cyan } = glow;

/** Inset glows on each edge (top, right, bottom, left); the layers rotate the colours around the screen. */
const edges = (top: string, right: string, bottom: string, left: string) =>
  [
    `inset 0 18px 34px -12px ${top}`,
    `inset -18px 0 34px -12px ${right}`,
    `inset 0 -18px 34px -12px ${bottom}`,
    `inset 18px 0 34px -12px ${left}`,
  ].join(", ");

const LAYERS = [edges(orange, pink, purple, cyan), edges(cyan, orange, pink, blue), edges(blue, cyan, orange, purple)];
const CYCLE_MS = 4800;

/** The iOS 18 Siri edge light: a soft rainbow glow around the screen while Duud is active. */
export function EdgeGlow({ active }: { active: boolean }) {
  const shown = useRef(new Animated.Value(0)).current;
  const cycle = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(cycle, { toValue: LAYERS.length, duration: CYCLE_MS, easing: Easing.linear, useNativeDriver: NATIVE }),
    );
    loop.start();
    return () => loop.stop();
  }, [cycle]);

  useEffect(() => {
    Animated.timing(shown, { toValue: active ? 1 : 0, duration: active ? 380 : 700, useNativeDriver: NATIVE }).start();
  }, [active, shown]);

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.passThrough, { opacity: shown }]}>
      {LAYERS.map((boxShadow, i) => {
        // Crossfade 0 -> 1 -> 2 -> 0: each layer peaks once per cycle.
        const peaks = LAYERS.map((_, j) => (j === i ? 1 : 0));
        const opacity = cycle.interpolate({
          inputRange: [...LAYERS.map((_, j) => j), LAYERS.length],
          outputRange: [...peaks, peaks[0] ?? 0],
        });
        return <Animated.View key={i} style={[StyleSheet.absoluteFill, styles.frame, { boxShadow, opacity }]} />;
      })}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  passThrough: { pointerEvents: "none" },
  // iPhone screens have rounded corners; the browser window does not.
  frame: { borderRadius: Platform.OS === "web" ? 0 : 44 },
});
