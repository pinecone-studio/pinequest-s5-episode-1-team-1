import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import type { BriefingPart } from "@bekhi/contracts";
import { type Card, type DocumentFinding, isOverdue, shortWhen } from "@/services/assistant/cards";
import { finishDraft } from "@/services/google";
import { BRIEFING_PARTS, DEFAULT_BRIEFING, saveProfile } from "@/services/profile";
import { colors, radius } from "@/theme";

const MAX_ROWS = 8;

type IconName = keyof typeof Ionicons.glyphMap;

/** WMO weather code -> icon. */
function weatherIcon(code: number | null): IconName {
  if (code === null) return "partly-sunny";
  if (code === 0) return "sunny";
  if (code <= 2) return "partly-sunny";
  if (code === 3) return "cloudy";
  if (code === 45 || code === 48) return "cloud-outline";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95) return "thunderstorm";
  return "rainy";
}

const SCHEDULED_ICONS: Record<string, IconName> = {
  alarm: "alarm-outline",
  timer: "timer-outline",
  event: "calendar-outline",
  reminder: "notifications-outline",
};

/** The details of BEKHI's answer, laid out under it: to-dos, weather, mail, what is scheduled. */
export function ResultCards({ cards }: { cards: Card[] }) {
  return (
    <View style={styles.stack}>
      {cards.map((card, i) => (
        <ResultCard key={i} card={card} />
      ))}
    </View>
  );
}

function ResultCard({ card }: { card: Card }) {
  switch (card.kind) {
    case "weather":
      return (
        <View style={[styles.card, styles.weather]}>
          <Ionicons name={weatherIcon(card.code)} size={44} color={colors.label} />
          <View style={styles.flex}>
            <Text style={styles.temp}>
              {card.max}° <Text style={styles.tempLow}>/ {card.min}°</Text>
            </Text>
            <Text style={styles.secondary} numberOfLines={1}>
              {[card.condition && card.condition[0]!.toUpperCase() + card.condition.slice(1), card.place].filter(Boolean).join(" · ")}
            </Text>
          </View>
          <View style={styles.weatherSide}>
            <Text style={styles.secondary}>{shortWhen(card.date)}</Text>
            {card.rain !== null && (
              <Text style={styles.secondary}>
                <Ionicons name="water-outline" size={13} color={colors.secondaryLabel} /> {card.rain}%
              </Text>
            )}
          </View>
        </View>
      );
    case "todos":
      return (
        <View style={styles.card}>
          <Header icon="checkbox-outline" title="Хийх зүйлс" count={card.items.length} />
          {card.items.slice(0, MAX_ROWS).map((item, i) => {
            const late = !item.done && item.due_at !== null && isOverdue(item.due_at);
            return (
              <View key={i} style={styles.row}>
                <Ionicons
                  name={item.done ? "checkmark-circle" : "ellipse-outline"}
                  size={20}
                  color={item.done ? colors.success : colors.tertiaryLabel}
                />
                <Text style={[styles.rowTitle, item.done && styles.done]} numberOfLines={2}>
                  {item.title}
                </Text>
                {item.due_at && <Text style={[styles.when, late && { color: colors.warning }]}>{shortWhen(item.due_at)}</Text>}
              </View>
            );
          })}
          <More count={card.items.length} />
        </View>
      );
    case "scheduled":
      return (
        <View style={styles.card}>
          <Header icon="time-outline" title="Товлосон" count={card.items.length} />
          {card.items.slice(0, MAX_ROWS).map((item, i) => (
            <View key={i} style={styles.row}>
              <Ionicons name={SCHEDULED_ICONS[item.kind] ?? "notifications-outline"} size={18} color={colors.secondaryLabel} />
              <Text style={styles.rowTitle} numberOfLines={2}>
                {item.title}
              </Text>
              <Text style={styles.when}>{shortWhen(item.fire_at)}</Text>
            </View>
          ))}
          <More count={card.items.length} />
        </View>
      );
    case "emails":
      return (
        <View style={styles.card}>
          <Header icon="mail-outline" title="Имэйл" count={card.emails.length} />
          {card.emails.slice(0, MAX_ROWS).map((email, i) => (
            <View key={i} style={styles.mailRow}>
              <View style={[styles.unread, !email.unread && { backgroundColor: "transparent" }]} />
              <View style={styles.flex}>
                <Text style={styles.from} numberOfLines={1}>
                  {email.from || "—"}
                </Text>
                {email.subject !== "" && (
                  <Text style={styles.rowTitle} numberOfLines={1}>
                    {email.subject}
                  </Text>
                )}
                {email.snippet !== "" && (
                  <Text style={styles.secondary} numberOfLines={1}>
                    {email.snippet}
                  </Text>
                )}
              </View>
            </View>
          ))}
          <More count={card.emails.length} />
        </View>
      );
    case "news":
      return (
        <View style={styles.card}>
          <Header icon="newspaper-outline" title="Өнөөдрийн мэдээ" />
          {card.items.map((item, i) => (
            <Pressable
              key={i}
              accessibilityRole="link"
              onPress={() => void Linking.openURL(item.url)}
              style={({ pressed }) => [styles.newsRow, pressed && { opacity: 0.6 }]}
            >
              <View style={styles.flex}>
                <Text style={styles.rowTitle} numberOfLines={2}>
                  {item.title}
                </Text>
                {item.source !== "" && <Text style={styles.secondary}>{item.source}</Text>}
              </View>
              <Ionicons name="open-outline" size={16} color={colors.tertiaryLabel} />
            </Pressable>
          ))}
        </View>
      );
    case "briefing_choice":
      return <BriefingChoice told={card.parts} />;
    case "email_draft":
      return <EmailDraft card={card} />;
    case "document_check":
      return <DocumentCheck card={card} />;
    case "screen":
      return (
        <View style={[styles.card, styles.row]}>
          <Ionicons name="eye-outline" size={16} color={colors.accent} />
          <Text style={[styles.secondary, styles.flex]} numberOfLines={1}>
            Харсан цонх: {card.window}
          </Text>
        </View>
      );
    case "email":
      return (
        <View style={styles.card}>
          <Header icon="mail-open-outline" title={card.subject || "Имэйл"} />
          {card.from !== "" && <Text style={styles.from}>{card.from}</Text>}
          <Text selectable style={styles.body} numberOfLines={14}>
            {card.text.trim()}
          </Text>
        </View>
      );
  }
}

/** A Gmail draft BEKHI wrote: nothing is sent until the user says yes or taps Send. */
function EmailDraft({ card }: { card: Extract<Card, { kind: "email_draft" }> }) {
  const [state, setState] = useState<"draft" | "busy" | "sent" | "dropped">("draft");
  const [problem, setProblem] = useState<string | null>(null);

  async function finish(what: "send" | "delete") {
    setState("busy");
    const error = await finishDraft(card.draftId, what);
    setProblem(error);
    setState(error ? "draft" : what === "send" ? "sent" : "dropped");
  }

  return (
    <View style={styles.card}>
      <Header icon="create-outline" title={card.subject || "Имэйлийн ноорог"} />
      <Text style={styles.secondary} numberOfLines={1}>
        Хэнд: {card.to}
        {card.address && card.address !== card.to ? ` <${card.address}>` : ""}
      </Text>
      <Text selectable style={styles.body}>
        {card.body}
      </Text>
      {problem && <Text style={[styles.secondary, { color: colors.warning }]}>{problem}</Text>}
      {state === "sent" || state === "dropped" ? (
        <Text style={[styles.secondary, state === "sent" && { color: colors.success }]}>
          {state === "sent" ? "Илгээлээ." : "Болиулсан. Ноорог устлаа."}
        </Text>
      ) : (
        <View style={styles.saveRow}>
          <Text style={[styles.secondary, styles.flex]}>"Тийм" гэж хэлж ч болно.</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => void finish("delete")}
            disabled={state === "busy"}
            style={({ pressed }) => [styles.quiet, pressed && { opacity: 0.6 }]}
          >
            <Text style={styles.quietText}>Болих</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => void finish("send")}
            disabled={state === "busy"}
            style={({ pressed }) => [styles.save, pressed && { opacity: 0.6 }]}
          >
            <Text style={styles.saveText}>Илгээх</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

/** What the check found in a contract, errors first. A finding about many blanks opens to list them all. */
function DocumentCheck({ card }: { card: Extract<Card, { kind: "document_check" }> }) {
  const errors = card.findings.filter((f) => f.severity === "error").length;
  const warnings = card.findings.length - errors;
  const verdict =
    card.findings.length === 0
      ? "Алдаа олдсонгүй"
      : [errors > 0 && `${errors} алдаа`, warnings > 0 && `${warnings} анхаарах зүйл`].filter(Boolean).join(", ");
  return (
    <View style={styles.card}>
      <Header icon="document-text-outline" title={card.title} />
      {card.name !== "" && (
        <Text style={styles.secondary} numberOfLines={1}>
          {card.name}
        </Text>
      )}
      <View style={styles.row}>
        <Ionicons
          name={errors > 0 ? "close-circle" : warnings > 0 ? "alert-circle" : "checkmark-circle"}
          size={20}
          color={errors > 0 ? colors.danger : warnings > 0 ? colors.warning : colors.success}
        />
        <Text style={styles.rowTitle}>{verdict}</Text>
      </View>
      {card.findings.map((finding, i) => (
        <Finding key={i} finding={finding} />
      ))}
      <Text style={styles.more}>БЭХИ хуульч биш. Чухал гэрээг хуульчаар хянуулаарай.</Text>
    </View>
  );
}

function Finding({ finding }: { finding: DocumentFinding }) {
  const [open, setOpen] = useState(false);
  const error = finding.severity === "error";
  return (
    <View style={styles.finding}>
      <View style={[styles.severity, { backgroundColor: error ? colors.danger : colors.warning }]} />
      <View style={styles.flex}>
        <Text selectable style={styles.findingText}>
          {finding.clause !== "" && <Text style={styles.clause}>{finding.clause}. </Text>}
          {finding.text}
        </Text>
        {finding.items.length > 1 && (
          <Pressable accessibilityRole="button" onPress={() => setOpen(!open)} hitSlop={6}>
            <Text style={styles.toggle}>{open ? "Хураах" : `Бүгдийг харах (${finding.items.length})`}</Text>
          </Pressable>
        )}
        {open &&
          finding.items.map((item, i) => (
            <Text key={i} selectable style={styles.secondary}>
              • {item}
            </Text>
          ))}
      </View>
    </View>
  );
}

/** The briefing's question as buttons: pick what it tells every time, then save (or answer by voice). */
function BriefingChoice({ told }: { told: BriefingPart[] }) {
  const [picked, setPicked] = useState<BriefingPart[]>(told.length > 0 ? told : DEFAULT_BRIEFING);
  const [state, setState] = useState<"choosing" | "saving" | "saved" | "failed">("choosing");

  function toggle(part: BriefingPart) {
    setState("choosing");
    setPicked((now) => (now.includes(part) ? now.filter((p) => p !== part) : [...now, part]));
  }

  async function save() {
    setState("saving");
    setState((await saveProfile({ briefing: picked })) ? "saved" : "failed");
  }

  return (
    <View style={styles.card}>
      <Header icon="sunny-outline" title="Өдрийн тоймд юу хэлэх вэ?" />
      <View style={styles.chips}>
        {BRIEFING_PARTS.map(({ part, label }) => {
          const on = picked.includes(part);
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
      <View style={styles.saveRow}>
        <Text style={[styles.secondary, styles.flex, state === "failed" && { color: colors.warning }]}>
          {state === "saved" ? "Хадгаллаа. Дараагийн тойм ийм байна." : state === "failed" ? "Хадгалж чадсангүй." : "Дуугаар хариулж ч болно."}
        </Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => void save()}
          disabled={state === "saving" || state === "saved"}
          style={({ pressed }) => [styles.save, (pressed || state === "saved") && { opacity: 0.6 }]}
        >
          <Text style={styles.saveText}>{state === "saved" ? "Хадгалсан" : "Хадгалах"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Header({ icon, title, count }: { icon: IconName; title: string; count?: number }) {
  return (
    <View style={styles.header}>
      <Ionicons name={icon} size={16} color={colors.accent} />
      <Text style={styles.headerText} numberOfLines={1}>
        {title}
      </Text>
      {count !== undefined && <Text style={styles.count}>{count}</Text>}
    </View>
  );
}

function More({ count }: { count: number }) {
  return count > MAX_ROWS ? <Text style={styles.more}>+{count - MAX_ROWS}</Text> : null;
}

const styles = StyleSheet.create({
  stack: { gap: 10, marginTop: 14 },
  card: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.card,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 8,
  },
  flex: { flex: 1, minWidth: 0 },
  header: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 2 },
  headerText: { flex: 1, fontSize: 13, fontWeight: "700", color: colors.secondaryLabel, letterSpacing: 0.2 },
  count: { fontSize: 13, color: colors.tertiaryLabel },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  rowTitle: { flex: 1, fontSize: 16, lineHeight: 21, color: colors.label },
  done: { color: colors.tertiaryLabel, textDecorationLine: "line-through" },
  when: { fontSize: 13, color: colors.secondaryLabel },
  weather: { flexDirection: "row", alignItems: "center", gap: 14 },
  temp: { fontSize: 30, fontWeight: "700", color: colors.label, letterSpacing: -0.5 },
  tempLow: { fontSize: 20, fontWeight: "500", color: colors.secondaryLabel },
  weatherSide: { alignItems: "flex-end", gap: 4 },
  secondary: { fontSize: 13, lineHeight: 18, color: colors.secondaryLabel },
  mailRow: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  unread: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent, marginTop: 6 },
  from: { fontSize: 14, fontWeight: "700", color: colors.label },
  body: { fontSize: 15, lineHeight: 21, color: colors.label },
  more: { fontSize: 13, color: colors.tertiaryLabel },
  newsRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 2 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
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
  saveRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 4 },
  save: { height: 38, paddingHorizontal: 16, borderRadius: radius.chip, alignItems: "center", justifyContent: "center", backgroundColor: colors.accent },
  saveText: { fontSize: 14, fontWeight: "700", color: colors.background },
  quiet: {
    height: 38,
    paddingHorizontal: 14,
    borderRadius: radius.chip,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  quietText: { fontSize: 14, fontWeight: "600", color: colors.secondaryLabel },
  finding: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  severity: { width: 3, alignSelf: "stretch", borderRadius: 2 },
  findingText: { fontSize: 15, lineHeight: 21, color: colors.label },
  clause: { fontWeight: "700", color: colors.secondaryLabel },
  toggle: { fontSize: 13, fontWeight: "600", color: colors.accent, marginTop: 4 },
});
