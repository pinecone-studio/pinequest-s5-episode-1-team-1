import { useEffect, useRef } from "react";
import { Animated, Platform, StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Svg, { Defs, RadialGradient, Rect, Stop } from "react-native-svg";
import { colors, glow } from "@/theme";

const NATIVE = Platform.OS !== "web";

/** Deep night gradient, with a glow behind the orb that brightens while BEKHI is active. */
export function Backdrop({ active }: { active: boolean }) {
  const lit = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(lit, { toValue: active ? 1 : 0, duration: 700, useNativeDriver: NATIVE }).start();
  }, [active, lit]);

  return (
    <View style={[StyleSheet.absoluteFill, styles.passThrough]}>
      <LinearGradient colors={[colors.backgroundTop, colors.backgroundBottom]} style={StyleSheet.absoluteFill} />
      <Animated.View style={[styles.glow, { opacity: lit.interpolate({ inputRange: [0, 1], outputRange: [0.45, 1] }) }]}>
        <Svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          <Defs>
            <RadialGradient id="bekhiBackdrop" cx="50" cy="100" r="62" gradientUnits="userSpaceOnUse">
              <Stop offset="0" stopColor={glow.purple} stopOpacity={0.42} />
              <Stop offset="0.45" stopColor={glow.blue} stopOpacity={0.14} />
              <Stop offset="1" stopColor={glow.blue} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x="0" y="0" width="100" height="100" fill="url(#bekhiBackdrop)" />
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  passThrough: { pointerEvents: "none" },
  glow: { position: "absolute", left: 0, right: 0, bottom: 0, height: "60%" },
});
