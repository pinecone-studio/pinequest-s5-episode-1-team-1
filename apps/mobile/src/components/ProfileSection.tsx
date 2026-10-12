import { useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, type TextStyle, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { BriefingPart } from "@bekhi/contracts";
import { BRIEFING_PARTS, DEFAULT_BRIEFING, loadProfile, type Profile, saveProfile } from "@/services/profile";
import { colors, radius } from "@/theme";
import { settingStyles as s } from "./settingStyles";

const NO_FOCUS_RING = Platform.OS === "web" ? ({ outlineStyle: "none" } as unknown as TextStyle) : null;

/**
 * In Settings: who the user is to BEKHI (name, city) and what the day's briefing tells, saved for the
 * account at once (services/profile.ts). The same is set by voice: "Намайг Нандин гэдэг".
 * `shown`: the sheet is open, so the profile is read again.
 */
export function ProfileSection({ shown }: { shown: boolean }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!shown) return;
    void loadProfile().then((p) => {
      setProfile(p);
      setName(p?.name ?? "");
      setCity(p?.city ?? "");
    });
  }, [shown]);

  if (!profile) return null;
  const parts = profile.briefing ?? DEFAULT_BRIEFING;

  async function save(changes: Partial<Profile>) {
    const saved = await saveProfile(changes);
    setFailed(saved === null);
    if (saved) setProfile(saved);
  }

  function toggle(part: BriefingPart) {
    const next = parts.includes(part) ? parts.filter((p) => p !== part) : [...parts, part];
    setProfile({ ...profile!, briefing: next }); // at once; the saved order comes back
    void save({ briefing: next });
  }

  return (
    <>
      <Text style={s.section}>Таны тухай</Text>
      <View style={s.card}>
        <Field
          label="Нэр"
          value={name}
          onChange={setName}
          onDone={() => name.trim() !== (profile.name ?? "") && void save({ name: name.trim() })}
          placeholder="BEKHI таныг юу гэж дуудах вэ?"
        />
        <View style={styles.divider} />
        <Field
          label="Хот"
          value={city}
          onChange={setCity}
          onDone={() => city.trim() !== (profile.city ?? "") && void save({ city: city.trim() })}
          placeholder="Цаг агаарыг хаанахаар хэлэх вэ?"
        />
      </View>

      <Text style={s.section}>Өдрийн тойм</Text>
      <View style={s.card}>
        <Text style={s.body}>"Өглөөний мэнд" гэхэд BEKHI эдгээрийг хэлж, дэлгэцэнд харуулна.</Text>
        <View style={styles.chips}>
          {BRIEFING_PARTS.map(({ part, label }) => {
            const on = parts.includes(part);
            return (
              <Pressable
                key={part}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                onPress={() => toggle(part)}
                style={[styles.chip, on && styles.chipOn]}
              >
                {on && <Ionicons name="checkmark" size={14} color={colors.background} />}
                <Text style={[styles.chipText, on && { color: colors.background }]}>{label}</Text>
              </Pressable>
            );
          })}
        </View>
        {failed && <Text style={[s.hint, { color: colors.warning, marginTop: 8 }]}>Хадгалж чадсангүй. Дахин оролдоно уу.</Text>}
      </View>
    </>
  );
}

function Field({ label, value, onChange, onDone, placeholder }: {
  label: string;
  value: string;
  onChange(text: string): void;
  onDone(): void;
  placeholder: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={[styles.input, NO_FOCUS_RING]}
        value={value}
        onChangeText={onChange}
        onBlur={onDone}
        onSubmitEditing={onDone}
        placeholder={placeholder}
        placeholderTextColor={colors.tertiaryLabel}
        selectionColor={colors.accent}
        keyboardAppearance="dark"
        maxLength={label === "Нэр" ? 40 : 60}
        accessibilityLabel={label}
        returnKeyType="done"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  field: { flexDirection: "row", alignItems: "center", gap: 12 },
  fieldLabel: { width: 44, fontSize: 15, color: colors.secondaryLabel },
  input: { flex: 1, minWidth: 0, height: 40, fontSize: 16, color: colors.label },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: 4 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.chip,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  chipOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { fontSize: 14, color: colors.label },
});
