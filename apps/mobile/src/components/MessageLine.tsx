import { StyleSheet, Text, View } from "react-native";
import type { ChatMessage } from "@/store/assistant";
import { colors } from "@/theme";

/** One line of the conversation, Siri style: your words small and grey, Duud's answer large and white. */
export function MessageLine({ message, dim }: { message: ChatMessage; dim: boolean }) {
  const { role, text, tone, understood } = message;
  if (role === "user") {
    return (
      <View style={[styles.userRow, dim && styles.dim]}>
        <Text selectable style={styles.user}>
          {text}
        </Text>
        {understood && <Text style={styles.understood}>Ойлгосон: {understood}</Text>}
      </View>
    );
  }
  const accent = tone === "error" ? colors.danger : tone === "warning" ? colors.warning : null;
  return (
    <View style={[styles.duudRow, accent && [styles.flagged, { borderLeftColor: accent }], dim && styles.dim]}>
      <Text selectable style={styles.duud}>
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  userRow: { alignItems: "flex-end", gap: 4, paddingLeft: 48 },
  user: { fontSize: 17, lineHeight: 23, color: colors.secondaryLabel, textAlign: "right" },
  understood: { fontSize: 13, color: colors.tertiaryLabel, textAlign: "right" },
  duudRow: { paddingRight: 24 },
  duud: { fontSize: 22, lineHeight: 30, fontWeight: "600", color: colors.label, letterSpacing: -0.2 },
  flagged: { borderLeftWidth: 3, paddingLeft: 12 },
  dim: { opacity: 0.42 },
});
