import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { linkWithCode } from "@/services/sync/alarm-sync";
import { codeFromLink } from "@/services/sync/identity";
import { colors } from "@/theme";

/**
 * bekhi://link?code=... — the computer's QR code read with the phone's own camera app (the
 * installed app; Expo Go reads it from BEKHI's Settings instead). Joins the computer's account,
 * then goes on to BEKHI.
 */
export default function Link() {
  const { code } = useLocalSearchParams<{ code?: string }>();
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    const joined = code ? codeFromLink(`?code=${code}`) : null;
    setOk(joined !== null);
    // The code is kept at once; the device registers with the API once BEKHI connects.
    if (joined) void linkWithCode(joined).catch(() => {});
    const timer = setTimeout(() => router.replace("/"), joined ? 1200 : 2500);
    return () => clearTimeout(timer);
  }, [code]);

  return (
    <View style={styles.screen}>
      {ok !== null && (
        <>
          <Ionicons name={ok ? "checkmark-circle" : "alert-circle"} size={64} color={ok ? colors.success : colors.warning} />
          <Text style={styles.title}>{ok ? "Компьютертэй холбогдлоо" : "QR код буруу байна"}</Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", gap: 16, backgroundColor: colors.background },
  title: { fontSize: 20, fontWeight: "700", color: colors.label },
});
