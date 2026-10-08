import { Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { MN } from "@bekhi/contracts";
import { colors, glow } from "@/theme";

/** Yes / no before a call or message. */
export function ConfirmBar({ onAnswer }: { onAnswer(yes: boolean): void }) {
  return (
    <View style={styles.row}>
      <Pressable
        accessibilityRole="button"
        onPress={() => onAnswer(false)}
        style={({ pressed }) => [styles.button, styles.no, pressed && styles.pressed]}
      >
        <Text style={styles.label}>{MN.ui.confirmNo}</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => onAnswer(true)} style={({ pressed }) => [styles.yes, pressed && styles.pressed]}>
        <LinearGradient
          colors={[glow.pink, glow.purple, glow.blue]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.button}
        >
          <Text style={styles.label}>{MN.ui.confirmYes}</Text>
        </LinearGradient>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 20, paddingVertical: 10 },
  button: { height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  no: { flex: 1, backgroundColor: colors.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  yes: { flex: 1 },
  pressed: { opacity: 0.75 },
  label: { fontSize: 17, fontWeight: "600", color: colors.label },
});
