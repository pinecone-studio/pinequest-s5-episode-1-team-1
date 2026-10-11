import { useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { wakeKey } from "@/services/assistant/wake";
import type { Voice } from "@/services/speech/voices";
import { colors, radius } from "@/theme";
import { LinkSection } from "./LinkSection";
import { settingStyles as s } from "./settingStyles";

interface Props {
  live: boolean;
  voices: Voice[];
  voiceId: string | null;
  onChooseVoice(id: string): void;
  voiceReplies: boolean;
  onToggleVoiceReplies(): void;
  onOpenMap(): void;
}

type Gender = "эр" | "эм";

/** react-native-web paints the switched-on knob with its own teal unless told otherwise. */
const WEB_SWITCH = Platform.OS === "web" ? ({ activeThumbColor: colors.label } as object) : {};

/**
 * The one header button: everything that is set once lives here, so the main screen is only
 * the conversation and the orb. Voice replies and the voice, linking the phone and computer,
 * Google, and the map.
 */
export function Settings({ live, voices, voiceId, onChooseVoice, voiceReplies, onToggleVoiceReplies, onOpenMap }: Props) {
  const [open, setOpen] = useState(false);
  const [moreVoices, setMoreVoices] = useState(false);
  // Only voices that work on the current plan (the others would be read in the default voice anyway).
  const usable = voices.filter((v) => !v.needs_paid_plan);
  const current = usable.find((v) => v.id === voiceId);
  const gender: Gender | null = current?.gender === "эм" ? "эм" : current ? "эр" : null;

  function pickGender(g: Gender) {
    if (g === gender) return;
    const first = usable.find((v) => v.gender === g);
    if (first) onChooseVoice(first.id);
  }

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Тохиргоо"
        onPress={() => setOpen(true)}
        hitSlop={8}
        style={({ pressed }) => [styles.headerButton, pressed && { backgroundColor: colors.surfacePressed }]}
      >
        <Ionicons name="options-outline" size={20} color={colors.label} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.grabber} />
            <View style={styles.titleRow}>
              <Text style={styles.title}>Тохиргоо</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Хаах" onPress={() => setOpen(false)} hitSlop={10}>
                <Ionicons name="close-circle" size={28} color={colors.tertiaryLabel} />
              </Pressable>
            </View>
            <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
              <Text style={s.section}>Хариулт</Text>
              <View style={s.card}>
                <View style={styles.switchRow}>
                  <Text style={s.rowTitle}>Дуугаар хариулах</Text>
                  <Switch
                    value={voiceReplies}
                    onValueChange={onToggleVoiceReplies}
                    trackColor={{ false: colors.surfacePressed, true: colors.accent }}
                    thumbColor={colors.label}
                    {...WEB_SWITCH}
                    accessibilityLabel="Дуугаар хариулах"
                  />
                </View>
                {voiceReplies && usable.length > 0 && (
                  <>
                    <View style={styles.segment}>
                      {(["эм", "эр"] as const).map((g) => (
                        <Pressable
                          key={g}
                          accessibilityRole="button"
                          accessibilityState={{ selected: gender === g }}
                          onPress={() => pickGender(g)}
                          style={[styles.segmentItem, gender === g && styles.segmentSelected]}
                        >
                          <Text style={[styles.segmentText, gender === g && styles.segmentTextSelected]}>
                            {g === "эм" ? "Эмэгтэй хоолой" : "Эрэгтэй хоолой"}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                    <Pressable accessibilityRole="button" onPress={() => setMoreVoices(!moreVoices)} style={styles.more}>
                      <Text style={s.hint}>{moreVoices ? "Хураах" : `Өөр хоолой${current ? ` · одоо: ${current.name}` : ""}`}</Text>
                      <Ionicons name={moreVoices ? "chevron-up" : "chevron-down"} size={12} color={colors.tertiaryLabel} />
                    </Pressable>
                    {moreVoices && (
                      <View style={styles.chips}>
                        {usable
                          .filter((v) => gender === null || v.gender === gender)
                          .map((v) => (
                            <Pressable
                              key={v.id}
                              accessibilityRole="button"
                              accessibilityState={{ selected: v.id === voiceId }}
                              onPress={() => onChooseVoice(v.id)}
                              style={[styles.chip, v.id === voiceId && styles.chipSelected]}
                            >
                              <Text style={[styles.chipText, v.id === voiceId && { color: colors.background }]}>{v.name}</Text>
                            </Pressable>
                          ))}
                      </View>
                    )}
                  </>
                )}
              </View>

              {live && <LinkSection shown={open} />}

              <Text style={s.section}>Бусад</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setOpen(false);
                  onOpenMap();
                }}
                style={({ pressed }) => [s.card, styles.navRow, pressed && { backgroundColor: colors.surfacePressed }]}
              >
                <Ionicons name="map-outline" size={18} color={colors.label} />
                <Text style={[s.rowTitle, { flex: 1 }]}>Газрын зураг, зам</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.tertiaryLabel} />
              </Pressable>

              {Platform.OS === "web" && (
                <Text style={[s.hint, styles.footer]}>
                  Space дарж ярина{wakeKey() ? `. Өөр програм дээр байхдаа ${wakeKey()} дарвал БЭХИ гарч ирээд сонсоно` : ""}.
                  Ярьж дуусахад БЭХИ өөрөө ойлгоно.
                </Text>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  headerButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end", alignItems: "center" },
  sheet: {
    width: "100%",
    maxWidth: 560,
    maxHeight: "88%",
    backgroundColor: colors.sheet,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingTop: 10,
  },
  grabber: { alignSelf: "center", width: 36, height: 5, borderRadius: 3, backgroundColor: colors.tertiaryLabel, marginBottom: 6 },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 20 },
  title: { fontSize: 22, fontWeight: "700", color: colors.label },
  content: { paddingHorizontal: 16, paddingBottom: 32 },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  segment: { flexDirection: "row", gap: 8, marginTop: 14 },
  segmentItem: {
    flex: 1,
    height: 40,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  segmentSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  segmentText: { fontSize: 14, fontWeight: "600", color: colors.secondaryLabel },
  segmentTextSelected: { color: colors.background },
  more: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 12 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.chip, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  chipSelected: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { fontSize: 14, color: colors.label },
  navRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  footer: { textAlign: "center", marginTop: 22 },
});
