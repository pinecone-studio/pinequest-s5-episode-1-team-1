import { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { Voice } from "@/services/speech/voices";
import { colors, radius } from "@/theme";

interface Props {
  voices: Voice[];
  voiceId: string | null;
  onChoose(id: string): void;
}

/** Header chip with the current voice; opens a list of the ElevenLabs voices. */
export function VoicePicker({ voices, voiceId, onChoose }: Props) {
  const [open, setOpen] = useState(false);
  if (voices.length === 0) return null;
  const current = voices.find((v) => v.id === voiceId);
  const free = voices.filter((v) => !v.needs_paid_plan);
  const paid = voices.filter((v) => v.needs_paid_plan);

  function choose(id: string) {
    setOpen(false);
    onChoose(id);
  }

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Хоолой сонгох"
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.chip, pressed && { opacity: 0.6 }]}
      >
        <Ionicons name="sparkles" size={14} color={colors.accent} />
        <Text style={styles.chipText}>{current?.name.split(" ")[0] ?? "Хоолой"}</Text>
        <Ionicons name="chevron-down" size={12} color={colors.secondaryLabel} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.grabber} />
            <Text style={styles.title}>Хоолой сонгох</Text>
            <ScrollView style={styles.list}>
              <Text style={styles.section}>Үнэгүй</Text>
              {free.map((v) => (
                <Row key={v.id} voice={v} selected={v.id === voiceId} onPress={() => choose(v.id)} />
              ))}
              {paid.length > 0 && (
                <>
                  <Text style={styles.section}>Монгол хоолой · ElevenLabs-ийн төлбөртэй багц хэрэгтэй</Text>
                  {paid.map((v) => (
                    <Row key={v.id} voice={v} selected={v.id === voiceId} onPress={() => choose(v.id)} />
                  ))}
                </>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

function Row({ voice, selected, onPress }: { voice: Voice; selected: boolean; onPress(): void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [styles.row, selected && styles.rowSelected, pressed && styles.rowPressed]}
    >
      <View style={styles.rowText}>
        <Text style={[styles.name, voice.needs_paid_plan && { color: colors.tertiaryLabel }]}>{voice.name}</Text>
        <Text style={styles.gender}>{voice.gender}</Text>
      </View>
      {selected && <Ionicons name="checkmark" size={20} color={colors.accent} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    height: 36,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.chip,
    paddingHorizontal: 12,
  },
  chipText: { fontSize: 14, fontWeight: "600", color: colors.label },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end", alignItems: "center" },
  sheet: {
    width: "100%",
    maxWidth: 560,
    backgroundColor: colors.sheet,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingTop: 10,
    paddingBottom: 28,
    maxHeight: "78%",
  },
  grabber: { alignSelf: "center", width: 36, height: 5, borderRadius: 3, backgroundColor: colors.tertiaryLabel, marginBottom: 12 },
  title: { fontSize: 20, fontWeight: "700", color: colors.label, paddingHorizontal: 20, marginBottom: 6 },
  list: { paddingHorizontal: 10 },
  section: {
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 0.4,
    color: colors.tertiaryLabel,
    paddingHorizontal: 12,
    marginTop: 14,
    marginBottom: 4,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 13,
    borderRadius: 12,
  },
  rowSelected: { backgroundColor: colors.surface },
  rowPressed: { backgroundColor: colors.surfacePressed },
  rowText: { flexDirection: "row", alignItems: "baseline", gap: 8 },
  name: { fontSize: 17, color: colors.label },
  gender: { fontSize: 13, color: colors.tertiaryLabel },
});
