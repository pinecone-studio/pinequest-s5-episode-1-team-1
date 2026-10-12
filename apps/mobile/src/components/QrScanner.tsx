import { useEffect, useRef } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { CameraView, useCameraPermissions } from "expo-camera";
import { codeFromLink } from "@/services/sync/identity";
import { colors, radius } from "@/theme";

/** Full-screen camera that reads the computer's link QR code (Settings on the computer) and returns its code. */
export function QrScanner({ visible, onCode, onClose }: { visible: boolean; onCode(code: string): void; onClose(): void }) {
  const [permission, requestPermission] = useCameraPermissions();
  const found = useRef(false);

  useEffect(() => {
    if (!visible) return;
    found.current = false;
    if (permission && !permission.granted && permission.canAskAgain) void requestPermission();
  }, [visible, permission, requestPermission]);

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.screen}>
        {permission?.granted && (
          <CameraView
            style={StyleSheet.absoluteFill}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={({ data }) => {
              if (found.current) return;
              const code = codeFromLink(data);
              if (!code) return; // some other QR code: keep looking
              found.current = true;
              onCode(code);
            }}
          />
        )}
        <SafeAreaView style={styles.overlay} edges={["top", "bottom"]}>
          <Pressable accessibilityRole="button" accessibilityLabel="Хаах" onPress={onClose} hitSlop={12} style={styles.close}>
            <Ionicons name="close" size={26} color={colors.label} />
          </Pressable>
          <View style={styles.frame} />
          <View style={styles.hintBox}>
            {permission && !permission.granted ? (
              <>
                <Text style={styles.hint}>QR уншуулахын тулд камерын зөвшөөрөл хэрэгтэй.</Text>
                <Pressable accessibilityRole="button" onPress={() => void requestPermission()} style={styles.button}>
                  <Text style={styles.buttonText}>Зөвшөөрөх</Text>
                </Pressable>
              </>
            ) : (
              <Text style={styles.hint}>Компьютер дээрх BEKHI → Тохиргоо хэсэгт гарсан QR кодыг энд багтааж харуулна уу.</Text>
            )}
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#000" },
  overlay: { flex: 1, alignItems: "center", justifyContent: "space-between" },
  close: {
    alignSelf: "flex-end",
    margin: 16,
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0,0,0,0.5)",
  },
  frame: { width: 250, height: 250, borderRadius: 28, borderWidth: 3, borderColor: "rgba(255,255,255,0.9)" },
  hintBox: { alignItems: "center", gap: 14, padding: 24, marginBottom: 24 },
  hint: { fontSize: 16, lineHeight: 22, color: colors.label, textAlign: "center", textShadowColor: "#000", textShadowRadius: 6 },
  button: { height: 44, paddingHorizontal: 22, borderRadius: radius.chip, alignItems: "center", justifyContent: "center", backgroundColor: colors.accent },
  buttonText: { fontSize: 15, fontWeight: "700", color: colors.background },
});
