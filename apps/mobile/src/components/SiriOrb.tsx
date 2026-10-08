import { useEffect, useRef } from "react";
import { Animated, Easing, Platform, Pressable, StyleSheet, View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, RadialGradient, Stop } from "react-native-svg";
import { Ionicons } from "@expo/vector-icons";
import { glow } from "@/theme";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

const NATIVE = Platform.OS !== "web";
const CLOCK_MS = 60_000;

// Soft colour blobs orbiting inside the orb. Periods divide 60 s, so the shared clock loops seamlessly.
const BLOBS = [
  { color: glow.purple, size: 1.05, offset: 0.04, period: 20, reverse: false },
  { color: glow.blue, size: 0.84, offset: 0.16, period: 10, reverse: true },
  { color: glow.pink, size: 0.8, offset: 0.17, period: 6, reverse: false },
  { color: glow.orange, size: 0.62, offset: 0.2, period: 12, reverse: false },
  { color: glow.cyan, size: 0.6, offset: 0.19, period: 15, reverse: true },
] as const;

const ENERGY: Record<OrbState, number> = { idle: 0, listening: 0.7, thinking: 0.85, speaking: 0.75 };
const PULSE: Record<OrbState, number> = { idle: 0.45, listening: 0, thinking: 0.6, speaking: 1 };

interface Props {
  state: OrbState;
  /** Microphone level 0..1 while listening (drives the orb's size). */
  level: Animated.Value;
  size?: number;
  disabled?: boolean;
  accessibilityLabel: string;
  onPress(): void;
}

/** The Siri-style orb: tap to talk. Breathes when idle, follows the voice, swirls while thinking. */
export function SiriOrb({ state, level, size = 92, disabled, accessibilityLabel, onPress }: Props) {
  const clock = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  const energy = useRef(new Animated.Value(0)).current;
  const pulseAmount = useRef(new Animated.Value(PULSE.idle)).current;
  const thinking = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const spin = Animated.loop(
      Animated.timing(clock, { toValue: 1, duration: CLOCK_MS, easing: Easing.linear, useNativeDriver: NATIVE }),
    );
    const breathe = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 520, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE }),
        Animated.timing(pulse, { toValue: 0, duration: 640, easing: Easing.inOut(Easing.sin), useNativeDriver: NATIVE }),
      ]),
    );
    spin.start();
    breathe.start();
    return () => {
      spin.stop();
      breathe.stop();
    };
  }, [clock, pulse]);

  useEffect(() => {
    const ease = { duration: 420, easing: Easing.out(Easing.cubic), useNativeDriver: NATIVE };
    Animated.parallel([
      Animated.timing(energy, { toValue: ENERGY[state], ...ease }),
      Animated.timing(pulseAmount, { toValue: PULSE[state], ...ease }),
      Animated.timing(thinking, { toValue: state === "thinking" ? 1 : 0, ...ease }),
    ]).start();
  }, [state, energy, pulseAmount, thinking]);

  const beat = Animated.multiply(Animated.multiply(pulse, pulseAmount), 0.07);
  const scale = Animated.add(1, Animated.add(Animated.multiply(energy, 0.06), Animated.add(Animated.multiply(level, 0.34), beat)));
  const haloScale = Animated.add(0.9, Animated.add(Animated.multiply(energy, 0.18), Animated.multiply(level, 0.45)));
  const haloOpacity = Animated.add(0.32, Animated.multiply(energy, 0.6));
  const turn = (period: number, reverse: boolean) =>
    clock.interpolate({ inputRange: [0, 1], outputRange: ["0deg", `${(reverse ? -360 : 360) * (CLOCK_MS / 1000 / period)}deg`] });
  const box = size * 2;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      disabled={disabled}
      hitSlop={12}
      style={[styles.hit, { width: box, height: box }]}
    >
      <Animated.View style={[styles.center, styles.passThrough, { width: box, height: box, opacity: haloOpacity, transform: [{ scale: haloScale }] }]}>
        <Svg width={box} height={box} viewBox="0 0 100 100">
          <Defs>
            <RadialGradient id="bekhiHalo" cx="50" cy="50" r="50" gradientUnits="userSpaceOnUse">
              <Stop offset="0.25" stopColor={glow.purple} stopOpacity={0.55} />
              <Stop offset="0.55" stopColor={glow.blue} stopOpacity={0.22} />
              <Stop offset="1" stopColor={glow.blue} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Circle cx="50" cy="50" r="50" fill="url(#bekhiHalo)" />
        </Svg>
      </Animated.View>

      <Animated.View style={[styles.orb, { width: size, height: size, borderRadius: size / 2, transform: [{ scale }] }]}>
        {BLOBS.map((b, i) => (
          <Animated.View key={b.color} style={[StyleSheet.absoluteFill, { transform: [{ rotate: turn(b.period, b.reverse) }] }]}>
            <Svg width={size} height={size} viewBox="0 0 100 100">
              <Defs>
                <RadialGradient id={`bekhiBlob${i}`} cx="50%" cy="50%" r="50%">
                  <Stop offset="0" stopColor={b.color} stopOpacity={0.95} />
                  <Stop offset="0.5" stopColor={b.color} stopOpacity={0.55} />
                  <Stop offset="1" stopColor={b.color} stopOpacity={0} />
                </RadialGradient>
              </Defs>
              <Circle cx={50 + b.offset * 100} cy="50" r={b.size * 50} fill={`url(#bekhiBlob${i})`} />
            </Svg>
          </Animated.View>
        ))}

        {/* Thinking: a bright arc sweeps around the rim. */}
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: thinking, transform: [{ rotate: turn(1.5, false) }] }]}>
          <Svg width={size} height={size} viewBox="0 0 100 100">
            <Defs>
              <LinearGradient id="bekhiComet" x1="0" y1="0" x2="1" y2="1">
                <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.95} />
                <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
              </LinearGradient>
            </Defs>
            <Circle cx="50" cy="50" r="45" stroke="url(#bekhiComet)" strokeWidth={4} strokeLinecap="round" strokeDasharray="80 300" fill="none" />
          </Svg>
        </Animated.View>

        {/* Glass: a soft highlight and a thin rim. */}
        <Svg width={size} height={size} viewBox="0 0 100 100" style={StyleSheet.absoluteFill}>
          <Defs>
            <RadialGradient id="bekhiShine" cx="34" cy="26" r="46" gradientUnits="userSpaceOnUse">
              <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.5} />
              <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Circle cx="50" cy="50" r="50" fill="url(#bekhiShine)" />
        </Svg>
        <View style={[StyleSheet.absoluteFill, styles.passThrough, styles.rim, { borderRadius: size / 2 }]} />

        {state === "idle" && (
          <View style={[StyleSheet.absoluteFill, styles.center, styles.passThrough]}>
            <Ionicons name="mic" size={size * 0.32} color="rgba(255,255,255,0.95)" />
          </View>
        )}
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: { alignItems: "center", justifyContent: "center" },
  center: { position: "absolute", alignItems: "center", justifyContent: "center" },
  passThrough: { pointerEvents: "none" },
  orb: { overflow: "hidden", backgroundColor: "#160F38" },
  rim: { borderWidth: 1, borderColor: "rgba(255,255,255,0.24)" },
});
