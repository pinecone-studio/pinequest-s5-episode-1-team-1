import { useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, type TextStyle, View } from "react-native";
import { googleStatus, linkGoogle, unlinkGoogle, type GoogleStatus } from "@/services/google";
import { linkWithCode, syncCode } from "@/services/sync/alarm-sync";
import { colors, radius } from "@/theme";
import { settingStyles as s } from "./settingStyles";

const NO_FOCUS_RING = Platform.OS === "web" ? ({ outlineStyle: "none" } as unknown as TextStyle) : null;

type Status = { kind: "idle" } | { kind: "busy" } | { kind: "done" } | { kind: "error"; message: string };

/**
 * In Settings: the sync code that joins the user's phone and computer (alarms and timers ring on
 * both, the same to-do list, commands from one to the other), and the Google link (Gmail, Tasks).
 * `shown`: the sheet is open, so the code and the Google link are read again.
 */
export function LinkSection({ shown }: { shown: boolean }) {
  const [code, setCode] = useState("");
  const [mine, setMine] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [googleNote, setGoogleNote] = useState<string | null>(null);
  const [waitingForGoogle, setWaitingForGoogle] = useState(false);

  useEffect(() => {
    if (!shown) return;
    setMine(syncCode());
    setCode("");
    setStatus({ kind: "idle" });
    setGoogleNote(null);
    void googleStatus().then(setGoogle);
  }, [shown]);

  // After the Google sign-in window opens: check every few seconds until the link shows up.
  useEffect(() => {
    if (!shown || !waitingForGoogle) return;
    const timer = setInterval(() => {
      void googleStatus().then((next) => {
        if (!next?.linked) return;
        setGoogle(next);
        setWaitingForGoogle(false);
      });
    }, 2500);
    const giveUp = setTimeout(() => setWaitingForGoogle(false), 180_000);
    return () => {
      clearInterval(timer);
      clearTimeout(giveUp);
    };
  }, [shown, waitingForGoogle]);

  async function connectGoogle() {
    setGoogleNote(null);
    const problem = await linkGoogle();
    if (problem) setGoogleNote(problem);
    else setWaitingForGoogle(true);
  }

  async function disconnectGoogle() {
    await unlinkGoogle();
    setGoogle(await googleStatus());
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
      <Text style={s.section}>Утас, компьютер холбох</Text>
      <View style={s.card}>
        <Text style={s.body}>
          Хоёулан дээр нь нэг код байвал сэрүүлэг, хийх зүйлс хоёуланд нь харагдаж, утаснаасаа компьютерээ удирдана.
        </Text>
        <Text style={styles.label}>Таны код</Text>
        <Text style={styles.code} selectable>
          {mine}
        </Text>
        <Text style={styles.label}>Нөгөө төхөөрөмжийнхөө кодыг энд оруулна</Text>
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
            accessibilityLabel="Нөгөө төхөөрөмжийн код"
          />
          <Pressable
            accessibilityRole="button"
            onPress={() => void link()}
            disabled={status.kind === "busy" || code.trim().length === 0}
            style={({ pressed }) => [styles.button, (pressed || code.trim().length === 0) && { opacity: 0.6 }]}
          >
            <Text style={styles.buttonText}>Холбох</Text>
          </Pressable>
        </View>
        {status.kind === "done" && <Text style={[styles.status, { color: colors.success }]}>Холбогдлоо.</Text>}
        {status.kind === "error" && <Text style={[styles.status, { color: colors.warning }]}>{status.message}</Text>}
      </View>

      {google?.available && (
        <>
          <Text style={s.section}>Google (Gmail, Tasks)</Text>
          <View style={s.card}>
            <View style={styles.row}>
              <Text style={[s.rowTitle, { flex: 1 }]} numberOfLines={1}>
                {google.linked ? google.email ?? "Холбогдсон" : waitingForGoogle ? "Google цонхонд нэвтэрнэ үү…" : "Холбогдоогүй"}
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => void (google.linked ? disconnectGoogle() : connectGoogle())}
                style={({ pressed }) => [google.linked ? styles.quiet : styles.button, pressed && { opacity: 0.7 }]}
              >
                <Text style={google.linked ? styles.quietText : styles.buttonText}>{google.linked ? "Салгах" : "Холбох"}</Text>
              </Pressable>
            </View>
            {googleNote && <Text style={[styles.status, { color: colors.warning }]}>{googleNote}</Text>}
            <Text style={[s.hint, { marginTop: 10 }]}>
              Имэйлээ асуухад БЭХИ уншиж өгнө (зөвхөн уншина). Хийх зүйлс тань Google Tasks-тэй нэг жагсаалт болно.
            </Text>
          </View>
        </>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, color: colors.tertiaryLabel, marginTop: 14, marginBottom: 6 },
  code: { fontSize: 24, fontWeight: "700", letterSpacing: 2, color: colors.label, fontVariant: ["tabular-nums"] },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  input: {
    flex: 1,
    minWidth: 0,
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
  quiet: { height: 44, paddingHorizontal: 16, borderRadius: radius.chip, alignItems: "center", justifyContent: "center", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  quietText: { fontSize: 15, fontWeight: "600", color: colors.secondaryLabel },
  status: { fontSize: 13, marginTop: 8 },
});
