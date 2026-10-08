import { useState } from "react";
import { Modal, Platform, Pressable, StyleSheet, Text, TextInput, type TextStyle, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { linkWithCode, syncCode } from "@/services/sync/alarm-sync";
import { colors, radius } from "@/theme";

const NO_FOCUS_RING = Platform.OS === "web" ? ({ outlineStyle: "none" } as unknown as TextStyle) : null;

type Status = { kind: "idle" } | { kind: "busy" } | { kind: "done" } | { kind: "error"; message: string };

/**
 * Header button: this device's sync code, and a field for another device's code. Devices
 * with the same code share alarms and timers (alarm-sync.ts).
 */
export function SyncLink({ live }: { live: boolean }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [mine, setMine] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  if (!live) return null;

  function show() {
    setMine(syncCode());
    setCode("");
    setStatus({ kind: "idle" });
    setOpen(true);
  }

  async function link() {
    setStatus({ kind: "busy" });
    try {
      if (!(await linkWithCode(code))) {
        setStatus({ kind: "error", message: "Код 12 тэмдэгттэй байна, жишээ нь ABCD-EFGH-JKMN." });
        return;
      }
      setMine(syncCode());
      setCode("");
      setStatus({ kind: "done" });
    } catch {
      setStatus({ kind: "error", message: "Сервертэй холбогдож чадсангүй. Дахин оролдоно уу." });
    }
  }

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Төхөөрөмж холбох"
        onPress={show}
        hitSlop={8}
        style={({ pressed }) => [styles.round, pressed && { backgroundColor: colors.surfacePressed }]}
      >
        <Ionicons name="link" size={18} color={colors.label} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          <Pressable style={styles.sheet} onPress={() => {}}>
            <View style={styles.grabber} />
            <Text style={styles.title}>Төхөөрөмж холбох</Text>
            <Text style={styles.body}>
              Утас, компьютер дээрээ ижил код оруулбал сэрүүлэг, таймер бүгд дээр нь зэрэг дуугарна.
            </Text>

            <Text style={styles.section}>Энэ төхөөрөмжийн код</Text>
            <Text style={styles.code} selectable>
              {mine}
            </Text>

            <Text style={styles.section}>Өөр төхөөрөмжийн код</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, NO_FOCUS_RING]}
                value={code}
                onChangeText={setCode}
                onSubmitEditing={() => void link()}
                placeholder="ABCD-EFGH-JKMN"
                placeholderTextColor={colors.tertiaryLabel}
                selectionColor={colors.accent}
                keyboardAppearance="dark"
                autoCapitalize="characters"
                autoCorrect={false}
                maxLength={20}
                accessibilityLabel="Өөр төхөөрөмжийн код"
              />
              <Pressable
                accessibilityRole="button"
                onPress={() => void link()}
                disabled={status.kind === "busy" || code.trim().length === 0}
                style={({ pressed }) => [styles.button, pressed && { opacity: 0.7 }]}
              >
                <Text style={styles.buttonText}>Холбох</Text>
              </Pressable>
            </View>
            {status.kind === "done" && <Text style={[styles.status, { color: colors.success }]}>Холбогдлоо.</Text>}
            {status.kind === "error" && <Text style={[styles.status, { color: colors.warning }]}>{status.message}</Text>}
            <Text style={styles.hint}>
              Утас БЭХИ нээлттэй үед бусад төхөөрөмжийн сэрүүлгийг татаж авна. Компьютер дээр БЭХИ API ажиллаж байх хэрэгтэй.
            </Text>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  round: {
    width: 36,
    height: 36,
    borderRadius: 18,
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
    backgroundColor: colors.sheet,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingTop: 10,
    paddingBottom: 28,
    paddingHorizontal: 20,
  },
  grabber: { alignSelf: "center", width: 36, height: 5, borderRadius: 3, backgroundColor: colors.tertiaryLabel, marginBottom: 12 },
  title: { fontSize: 20, fontWeight: "700", color: colors.label, marginBottom: 6 },
  body: { fontSize: 15, lineHeight: 21, color: colors.secondaryLabel },
  section: { fontSize: 12, fontWeight: "600", letterSpacing: 0.4, color: colors.tertiaryLabel, marginTop: 18, marginBottom: 6 },
  code: { fontSize: 26, fontWeight: "700", letterSpacing: 2, color: colors.label, fontVariant: ["tabular-nums"] },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  input: {
    flex: 1,
    height: 44,
    paddingHorizontal: 14,
    borderRadius: radius.chip,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    color: colors.label,
    fontSize: 17,
    letterSpacing: 1,
  },
  button: { height: 44, paddingHorizontal: 18, borderRadius: radius.chip, alignItems: "center", justifyContent: "center", backgroundColor: colors.accent },
  buttonText: { fontSize: 15, fontWeight: "700", color: colors.background },
  status: { fontSize: 13, marginTop: 8 },
  hint: { fontSize: 12, lineHeight: 17, color: colors.tertiaryLabel, marginTop: 16 },
});
