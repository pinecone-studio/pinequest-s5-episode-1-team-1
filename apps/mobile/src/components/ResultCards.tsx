import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import type { BriefingPart } from "@bekhi/contracts";
import { tap } from "@/lib/haptics";
import { type Card, isOverdue, type Place, shortWhen } from "@/services/assistant/cards";
import { finishDraft } from "@/services/google";
import { formatDistance, formatDuration } from "@/services/maps/geo";
import { walkSeconds } from "@/services/maps/transit";
import { BRIEFING_PARTS, DEFAULT_BRIEFING, saveProfile } from "@/services/profile";
import { useAssistant } from "@/store/assistant";
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
    case "food_ideas":
      return <FoodIdeas ideas={card.ideas} />;
    case "recipe":
      return <Recipe card={card} />;
    case "restaurants":
      return <Restaurants query={card.query} places={card.places} />;
  }
}

const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const upper = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Dish ideas: each one cooked at home (its recipe) or eaten out (places nearby), as if the user said so. */
function FoodIdeas({ ideas }: { ideas: Extract<Card, { kind: "food_ideas" }>["ideas"] }) {
  const busy = useAssistant((s) => s.phase === "processing" || s.phase === "executing");

  function ask(text: string) {
    tap();
    void useAssistant.getState().submitText(text);
  }

  return (
    <View style={styles.card}>
      <Header icon="restaurant-outline" title="Юу идэх вэ?" />
      {ideas.map((idea, i) => (
        <View key={i} style={[styles.idea, i > 0 && styles.divided]}>
          <Text style={styles.dish}>{idea.dish}</Text>
          {idea.note !== "" && <Text style={styles.secondary}>{upper(idea.note)}</Text>}
          <View style={styles.ideaButtons}>
            <Pressable
              accessibilityRole="button"
              disabled={busy}
              onPress={() => ask(`${idea.dish} хийх аргыг хэлээч`)}
              style={({ pressed }) => [styles.chip, (pressed || busy) && { opacity: 0.6 }]}
            >
              <Ionicons name="flame-outline" size={14} color={colors.label} />
              <Text style={styles.chipText}>Гэртээ хийх</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              disabled={busy}
              onPress={() => ask(`Ойролцоо ${lower(idea.dish)} идэх газар олоод өгөөч`)}
              style={({ pressed }) => [styles.chip, (pressed || busy) && { opacity: 0.6 }]}
            >
              <Ionicons name="location-outline" size={14} color={colors.label} />
              <Text style={styles.chipText}>Гадуур идэх</Text>
            </Pressable>
          </View>
        </View>
      ))}
    </View>
  );
}

/** A recipe to cook along with: ingredients ticked off as they are ready, then the steps in order. */
function Recipe({ card }: { card: Extract<Card, { kind: "recipe" }> }) {
  const [ready, setReady] = useState<ReadonlySet<number>>(new Set());

  function toggle(i: number) {
    setReady((now) => {
      const next = new Set(now);
      if (!next.delete(i)) next.add(i);
      return next;
    });
  }

  return (
    <View style={styles.card}>
      <Header icon="restaurant-outline" title={card.dish} />
      <View style={styles.metaRow}>
        <View style={styles.meta}>
          <Ionicons name="people-outline" size={14} color={colors.secondaryLabel} />
          <Text style={styles.secondary}>{card.servings} хүн</Text>
        </View>
        <View style={styles.meta}>
          <Ionicons name="time-outline" size={14} color={colors.secondaryLabel} />
          <Text style={styles.secondary}>{formatDuration(card.minutes * 60)}</Text>
        </View>
      </View>
      {card.ingredients.length > 0 && (
        <>
          <Text style={styles.section}>Орц</Text>
          {card.ingredients.map((item, i) => {
            const on = ready.has(i);
            return (
              <Pressable
                key={i}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                onPress={() => toggle(i)}
                style={styles.row}
              >
                <Ionicons
                  name={on ? "checkmark-circle" : "ellipse-outline"}
                  size={20}
                  color={on ? colors.success : colors.tertiaryLabel}
                />
                <Text style={[styles.rowTitle, on && styles.done]}>{item}</Text>
              </Pressable>
            );
          })}
        </>
      )}
      <Text style={styles.section}>Хийх дараалал</Text>
      {card.steps.map((step, i) => (
        <View key={i} style={styles.step}>
          <View style={styles.stepNumber}>
            <Text style={styles.stepNumberText}>{i + 1}</Text>
          </View>
          <Text selectable style={[styles.body, styles.flex]}>
            {step}
          </Text>
        </View>
      ))}
    </View>
  );
}

/** A Google plus code ("WW84+4QX, ") at the start of an address: no use to a person. */
const PLUS_CODE = /^[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3},?\s*/i;
/** The longest destination the directions request takes. */
const MAX_DESTINATION = 200;

/** Places to eat nearby, nearest first; tapping one opens BEKHI's map with the walk there. */
function Restaurants({ query, places }: { query: string | null; places: Place[] }) {
  function showWay(place: Place) {
    tap();
    const destination = [place.name, place.address].filter(Boolean).join(", ").slice(0, MAX_DESTINATION);
    router.push({ pathname: "/map", params: { destination, mode: "walking" } });
  }

  return (
    <View style={styles.card}>
      <Header
        icon="restaurant-outline"
        title={query ? `${upper(query)} идэх газар` : "Ойрын хоолны газар"}
        count={places.length}
      />
      {places.map((place, i) => {
        const address = place.address?.replace(PLUS_CODE, "") ?? "";
        const details = [
          place.rating !== null ? `★ ${place.rating.toFixed(1)}${place.rating_count ? ` (${place.rating_count})` : ""}` : null,
          place.kind,
        ].filter(Boolean);
        return (
          <Pressable
            key={i}
            accessibilityRole="button"
            accessibilityHint="Зам харах"
            onPress={() => showWay(place)}
            style={({ pressed }) => [styles.place, i > 0 && styles.divided, pressed && { opacity: 0.6 }]}
          >
            <View style={styles.flex}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {place.name}
              </Text>
              {details.length > 0 && (
                <Text style={styles.secondary} numberOfLines={1}>
                  {details.join(" · ")}
                </Text>
              )}
              {address !== "" && (
                <Text style={styles.secondary} numberOfLines={1}>
                  {address}
                </Text>
              )}
            </View>
            <View style={styles.placeSide}>
              <Text style={styles.when}>{formatDistance(place.distance_m)}</Text>
              <Text style={styles.secondary}>🚶 {formatDuration(walkSeconds(place.distance_m))}</Text>
              {place.open_now !== null && (
                <Text style={[styles.openNow, { color: place.open_now ? colors.success : colors.danger }]}>
                  {place.open_now ? "Нээлттэй" : "Хаалттай"}
                </Text>
              )}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
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
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: 10 },
  idea: { gap: 4 },
  dish: { fontSize: 17, fontWeight: "700", color: colors.label },
  ideaButtons: { flexDirection: "row", gap: 8, marginTop: 4 },
  metaRow: { flexDirection: "row", gap: 14 },
  meta: { flexDirection: "row", alignItems: "center", gap: 4 },
  section: { fontSize: 13, fontWeight: "700", color: colors.secondaryLabel, marginTop: 6 },
  step: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  stepNumber: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.accent,
    marginTop: 1,
  },
  stepNumberText: { fontSize: 12, fontWeight: "800", color: colors.background },
  place: { flexDirection: "row", alignItems: "center", gap: 10 },
  placeSide: { alignItems: "flex-end", gap: 2 },
  openNow: { fontSize: 12, fontWeight: "700" },
});
