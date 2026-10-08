import { useState } from "react";
import { Platform, Pressable, StyleSheet, TextInput, type TextStyle, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { colors, glow } from "@/theme";

// Chrome draws its own focus ring (outline-style: auto, which ignores outline-width) inside the
// rounded field. React Native's types only know solid/dotted/dashed, hence the cast.
const NO_FOCUS_RING = Platform.OS === "web" ? ({ outlineStyle: "none" } as unknown as TextStyle) : null;

interface Props {
  disabled: boolean;
  onSend(text: string): void;
  /** Back to talking. */
  onVoice(): void;
}

/** "Type to Siri": a glass text field that replaces the orb. */
export function TypeBar({ disabled, onSend, onVoice }: Props) {
  const [text, setText] = useState("");
  const canSend = text.trim().length > 0 && !disabled;

  function send() {
    if (!canSend) return;
    onSend(text);
    setText("");
  }

  return (
    <View style={styles.bar}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Дуугаар ярих"
        onPress={onVoice}
        hitSlop={8}
        style={({ pressed }) => [styles.round, pressed && styles.pressed]}
      >
        <Ionicons name="mic" size={20} color={colors.label} />
      </Pressable>
      <View style={styles.field}>
        <TextInput
          style={[styles.input, NO_FOCUS_RING]}
          value={text}
          onChangeText={setText}
          onSubmitEditing={send}
          placeholder="БЭХИ-д бичих…"
          placeholderTextColor={colors.tertiaryLabel}
          selectionColor={colors.accent}
          keyboardAppearance="dark"
          returnKeyType="send"
          submitBehavior="submit"
          autoFocus
          editable={!disabled}
          accessibilityLabel="Мессеж бичих"
        />
        <Pressable accessibilityRole="button" accessibilityLabel="Илгээх" onPress={send} disabled={!canSend} hitSlop={8}>
          <LinearGradient
            colors={[glow.pink, glow.purple, glow.blue]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.send, !canSend && styles.sendOff]}
          >
            <Ionicons name="arrow-up" size={18} color="#fff" />
          </LinearGradient>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12 },
  round: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  pressed: { backgroundColor: colors.surfacePressed },
  field: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    minHeight: 48,
    borderRadius: 24,
    paddingLeft: 18,
    paddingRight: 6,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  input: { flex: 1, fontSize: 17, color: colors.label, paddingVertical: 10 },
  send: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  sendOff: { opacity: 0.35 },
});
