import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { Backdrop } from "@/components/Backdrop";
import { ConfirmBar } from "@/components/ConfirmBar";
import { EdgeGlow } from "@/components/EdgeGlow";
import { MessageLine } from "@/components/MessageLine";
import { type OrbState, SiriOrb } from "@/components/SiriOrb";
import { TypeBar } from "@/components/TypeBar";
import { VoicePicker } from "@/components/VoicePicker";
import { notify, tap } from "@/lib/haptics";
import { SAMPLE_PHRASES } from "@/services/assistant/PreviewAssistantClient";
import { useVoiceInput } from "@/services/audio/useVoiceInput";
import { type Phase, useAssistant } from "@/store/assistant";
import { colors, MAX_CONTENT_WIDTH, radius } from "@/theme";

const NATIVE = Platform.OS !== "web";

/** Things to try once the backend is connected (the offline preview knows only SAMPLE_PHRASES). */
const LIVE_SUGGESTIONS = [
  "Маргааш 9 цагт ажилтайг минь сануулаарай.",
  "Маргааш хүрэм өмсөх хэрэгтэй юу?",
  "YouTube нээгээрэй.",
  "Ээж рүүгээ залга.",
] as const;

/** Older lines fade so the current exchange stands out, as in Siri. */
const RECENT_LINES = 2;

function orbState(phase: Phase, speaking: boolean): OrbState {
  if (phase === "listening") return "listening";
  if (phase === "processing" || phase === "executing") return "thinking";
  return speaking ? "speaking" : "idle";
}

function statusLabel(phase: Phase, speaking: boolean): string {
  switch (phase) {
    case "listening":
      return "Сонсож байна…";
    case "processing":
      return "Бодож байна…";
    case "executing":
      return "Хийж байна…";
    case "confirming":
      return "Тийм эсвэл Үгүй гэж хариулаарай";
    default:
      return speaking ? "Ярьж байна · товшвол таслана" : "Товшоод яриарай";
  }
}

/** Microphone dBFS -> 0..1 for the orb: quiet room ~0, normal speech ~0.5-1. */
const toLevel = (db: number | undefined) => (db === undefined ? 0 : Math.min(1, Math.max(0, (db + 55) / 40)));

export default function Chat() {
  const {
    phase,
    messages,
    client,
    voiceReplies,
    speechError,
    speaking,
    listenRequest,
    voices,
    voiceId,
    chooseVoice,
    connect,
    submitText,
    startListening,
    submitVoice,
    stopConversation,
    stopReply,
    answerConfirmation,
    toggleVoiceReplies,
    fail,
  } = useAssistant();
  const [typing, setTyping] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const level = useRef(new Animated.Value(0)).current;

  const listening = phase === "listening";
  const busy = phase === "processing" || phase === "executing";
  const confirming = phase === "confirming";
  const live = client.mode === "live";
  const active = listening || busy || speaking;

  const onLevel = useCallback(
    (db: number | undefined) => {
      Animated.timing(level, { toValue: toLevel(db), duration: 110, useNativeDriver: NATIVE }).start();
    },
    [level],
  );
  const voice = useVoiceInput(
    useCallback((uri: string | null) => void submitVoice(uri), [submitVoice]),
    stopConversation,
    onLevel,
  );

  useEffect(() => {
    void connect();
    // Back in the app after starting the PC's server or joining its Wi-Fi: look for it again.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active" && useAssistant.getState().client.mode !== "live") void connect();
    });
    return () => sub.remove();
  }, [connect]);

  useEffect(() => {
    if (!listening) Animated.timing(level, { toValue: 0, duration: 250, useNativeDriver: NATIVE }).start();
  }, [listening, level]);

  const listen = useCallback(async () => {
    startListening(); // also cuts off a reply that is still being spoken
    const started = await voice.start();
    if (started === "permission_denied") fail("Микрофоны зөвшөөрөл хэрэгтэй байна. Browser/утасны тохиргооноос зөвшөөрнө үү.");
    else if (started === "failed") fail("Микрофон асаахад алдаа гарлаа.");
  }, [startListening, voice, fail]);

  // Hands-free conversation: the reply has been spoken, so listen for the user's answer.
  const listenRef = useRef(listen);
  listenRef.current = listen;
  useEffect(() => {
    if (listenRequest > 0) void listenRef.current();
  }, [listenRequest]);

  useEffect(() => {
    if (phase === "success") notify("success");
    if (phase === "unavailable" || phase === "error") notify("warning");
  }, [phase]);

  async function onOrb() {
    tap();
    if (listening) {
      await submitVoice(await voice.stop());
      return;
    }
    setTyping(false);
    await listen();
  }

  async function cancelListening() {
    tap();
    await voice.stop();
    stopConversation(false);
  }

  const suggestions = live ? LIVE_SUGGESTIONS : SAMPLE_PHRASES;

  return (
    <View style={styles.screen}>
      <Backdrop active={active} />
      <SafeAreaView style={styles.flex} edges={["top", "bottom"]}>
        {/* Android draws edge to edge too, so the window does not shrink for the keyboard there either. */}
        <KeyboardAvoidingView style={styles.flex} behavior={NATIVE ? "padding" : undefined}>
          <View style={styles.header}>
            <View style={styles.brand}>
              <Text style={styles.wordmark}>BEKHI</Text>
              <View style={styles.connection}>
                <View style={[styles.dot, { backgroundColor: live ? colors.success : colors.warning }]} />
                <Text style={styles.connectionText}>{live ? "Холбогдсон" : "Туршилтын горим"}</Text>
              </View>
            </View>
            <View style={styles.headerActions}>
              <VoicePicker voices={voices} voiceId={voiceId} onChoose={chooseVoice} />
              <RoundButton
                icon={!voiceReplies ? "volume-mute" : speaking ? "volume-high" : "volume-medium"}
                label={voiceReplies ? "Дуугаар хариулахыг унтраах" : "Дуугаар хариулахыг асаах"}
                onPress={toggleVoiceReplies}
                small
              />
            </View>
          </View>

          {speechError && voiceReplies && (
            <View style={styles.noticeWrap}>
              <View style={styles.notice}>
                <Ionicons name="information-circle" size={16} color={colors.warning} />
                <Text style={styles.noticeText} numberOfLines={2}>
                  {speechError}
                </Text>
              </View>
            </View>
          )}

          <ScrollView
            ref={scroll}
            style={styles.flex}
            contentContainerStyle={styles.thread}
            onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            {messages.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.greeting}>Сайн байна уу</Text>
                <Text style={styles.subtitle}>Юугаар туслах вэ?</Text>
                <View style={styles.suggestions}>
                  {suggestions.map((p) => (
                    <Pressable
                      key={p}
                      onPress={() => submitText(p)}
                      disabled={busy}
                      style={({ pressed }) => [styles.suggestion, pressed && styles.suggestionPressed]}
                    >
                      <Text style={styles.suggestionText}>{p}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : (
              messages.map((m, i) => <MessageLine key={m.id} message={m} dim={i < messages.length - RECENT_LINES} />)
            )}
          </ScrollView>

          <View style={styles.bottom}>
            {confirming && <ConfirmBar onAnswer={answerConfirmation} />}
            {typing ? (
              <TypeBar disabled={busy || confirming} onSend={submitText} onVoice={() => void onOrb()} />
            ) : (
              <View style={styles.dock}>
                <Text style={styles.status}>{statusLabel(phase, speaking)}</Text>
                <View style={styles.dockRow}>
                  <RoundButton
                    icon={<MaterialCommunityIcons name="keyboard-outline" size={24} color={colors.label} />}
                    label="Бичиж асуух"
                    onPress={() => setTyping(true)}
                  />
                  <SiriOrb
                    state={orbState(phase, speaking)}
                    level={level}
                    disabled={busy || confirming}
                    accessibilityLabel={listening ? "Бичлэг зогсоох" : speaking ? "Таслаад ярих" : "Ярих"}
                    onPress={() => void onOrb()}
                  />
                  {listening ? (
                    <RoundButton icon="close" label="Болих" onPress={() => void cancelListening()} />
                  ) : speaking ? (
                    <RoundButton icon="stop" label="Уншихыг зогсоох" onPress={stopReply} />
                  ) : (
                    <View style={styles.roundSpacer} />
                  )}
                </View>
              </View>
            )}
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
      <EdgeGlow active={active} />
    </View>
  );
}

function RoundButton({
  icon,
  label,
  onPress,
  small,
}: {
  /** An Ionicons name, or a ready icon element. */
  icon: keyof typeof Ionicons.glyphMap | React.ReactElement;
  label: string;
  onPress(): void;
  small?: boolean;
}) {
  const size = small ? 36 : 48;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={8}
      style={({ pressed }) => [styles.round, { width: size, height: size, borderRadius: size / 2 }, pressed && styles.roundPressed]}
    >
      {typeof icon === "string" ? <Ionicons name={icon} size={small ? 18 : 22} color={colors.label} /> : icon}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  header: {
    width: "100%",
    maxWidth: MAX_CONTENT_WIDTH,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 6,
  },
  brand: { gap: 2 },
  wordmark: { fontSize: 24, fontWeight: "800", color: colors.label, letterSpacing: -0.5 },
  connection: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  connectionText: { fontSize: 12, color: colors.secondaryLabel },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 10 },
  noticeWrap: { width: "100%", maxWidth: MAX_CONTENT_WIDTH, alignSelf: "center", paddingHorizontal: 20 },
  notice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 4,
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 14,
    backgroundColor: "rgba(255,159,10,0.12)",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(255,159,10,0.35)",
  },
  noticeText: { flex: 1, fontSize: 13, lineHeight: 18, color: colors.label },
  thread: {
    width: "100%",
    maxWidth: MAX_CONTENT_WIDTH,
    alignSelf: "center",
    flexGrow: 1,
    justifyContent: "flex-end",
    gap: 18,
    paddingHorizontal: 22,
    paddingTop: 24,
    paddingBottom: 12,
  },
  empty: { flex: 1, justifyContent: "center", gap: 6, paddingVertical: 24 },
  greeting: { fontSize: 38, fontWeight: "800", color: colors.label, letterSpacing: -1 },
  subtitle: { fontSize: 20, color: colors.secondaryLabel, marginBottom: 18 },
  suggestions: { gap: 10 },
  suggestion: {
    alignSelf: "flex-start",
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.chip,
    paddingHorizontal: 16,
    paddingVertical: 11,
  },
  suggestionPressed: { backgroundColor: colors.surfacePressed },
  suggestionText: { fontSize: 15, color: colors.label },
  bottom: { width: "100%", maxWidth: MAX_CONTENT_WIDTH, alignSelf: "center" },
  dock: { alignItems: "center", paddingBottom: 4 },
  status: { fontSize: 14, fontWeight: "500", color: colors.secondaryLabel, marginBottom: -14 },
  dockRow: { width: "100%", flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 28 },
  round: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  roundPressed: { backgroundColor: colors.surfacePressed },
  roundSpacer: { width: 48, height: 48 },
});
