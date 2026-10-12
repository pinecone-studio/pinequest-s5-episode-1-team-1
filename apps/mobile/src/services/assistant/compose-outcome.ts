import { MN, type ActionRequest, type ActionResult, type ToolName } from "@bekhi/contracts";
import { NATIVE_UNAVAILABLE } from "@/services/ios-actions/codes";
import { formatWhenMn } from "@/lib/time";
import { toward } from "@/lib/mongolian";

/** "X боломжгүй" form and dative "X-д асуудал гарлаа" form (vowel harmony spelled out). */
const ACTION_MN: Record<ToolName, { verb: string; dative: string }> = {
  call_contact: { verb: "залгах", dative: "залгахад" },
  send_message: { verb: "мессеж бичих", dative: "мессеж бичихэд" },
  create_reminder: { verb: "сануулга үүсгэх", dative: "сануулга үүсгэхэд" },
  create_calendar_event: { verb: "календарьт нэмэх", dative: "календарьт нэмэхэд" },
  create_alarm: { verb: "сэрүүлэг тавих", dative: "сэрүүлэг тавихад" },
  create_note: { verb: "тэмдэглэл хадгалах", dative: "тэмдэглэл хадгалахад" },
  open_maps: { verb: "газрын зураг нээх", dative: "газрын зураг нээхэд" },
  find_bus_stops: { verb: "автобусны буудал хайх", dative: "автобусны буудал хайхад" },
  get_weather: { verb: "цаг агаар харах", dative: "цаг агаар харахад" },
  web_search: { verb: "хайлт хийх", dative: "хайлт хийхэд" },
  get_current_time: { verb: "цаг харах", dative: "цаг харахад" },
  open_url: { verb: "вэб хуудас нээх", dative: "вэб хуудас нээхэд" },
  open_app: { verb: "програм нээх", dative: "програм нээхэд" },
  set_timer: { verb: "таймер тавих", dative: "таймер тавихад" },
  list_reminders: { verb: "сануулгуудыг харах", dative: "сануулгуудыг харахад" },
  cancel_reminder: { verb: "сануулга цуцлах", dative: "сануулга цуцлахад" },
  computer_control: { verb: "компьютер удирдах", dative: "компьютер удирдахад" },
  add_todo: { verb: "жагсаалтад нэмэх", dative: "жагсаалтад нэмэхэд" },
  list_todos: { verb: "жагсаалт харах", dative: "жагсаалт харахад" },
  complete_todo: { verb: "тэмдэглэх", dative: "тэмдэглэхэд" },
  delete_todo: { verb: "устгах", dative: "устгахад" },
};

/**
 * Final Mongolian answer from REAL outcomes. Used by the preview client; the backend
 * owns this from Phase 3 (POST /assistant/actions/results).
 */
export function composeOutcome(actions: ActionRequest[], results: ActionResult[], nowIso: string): string {
  const parts = results.map((r) => {
    const action = actions.find((a) => a.id === r.action_id);
    return action ? sentenceFor(action, r, nowIso) : "";
  });
  return parts.filter(Boolean).join(" ");
}

function sentenceFor(action: ActionRequest, r: ActionResult, nowIso: string): string {
  const { verb, dative } = ACTION_MN[action.tool];
  switch (r.status) {
    case "succeeded":
      if (action.tool === "find_bus_stops") return stopsSentence(r.data?.stops);
      return successSentence(action, nowIso);
    case "handed_off":
      return handedOffSentence(action);
    case "cancelled":
      return "За, болиулчихлаа.";
    case "permission_denied":
      return MN.errors.permissionDenied;
    case "needs_clarification":
      return "Аль нь болохыг тодруулаад өгөөч.";
    case "unsupported":
      if (r.error_code === NATIVE_UNAVAILABLE.web) {
        return `Компьютерийн browser дээр ${verb} боломжгүй. Үүнийг iPhone дээр туршина.`;
      }
      if (r.error_code === NATIVE_UNAVAILABLE.expoGo) {
        return `Expo Go дээр ${verb} боломжгүй. Үүнд development build хэрэгтэй.`;
      }
      if (r.error_code === NATIVE_UNAVAILABLE.notBuilt) {
        return `${capitalize(verb)} үйлдэл одоохондоо бэлэн болоогүй байна.`;
      }
      return MN.errors.iosUnavailable;
    case "failed":
      return `${capitalize(dative)} асуудал гарлаа.`;
  }
}

function successSentence(action: ActionRequest, nowIso: string): string {
  switch (action.tool) {
    case "create_reminder":
      return `За, ${formatWhenMn(action.arguments.due_at, nowIso)} сануулъя.`;
    case "create_alarm":
      return `За, ${formatWhenMn(action.arguments.fire_at, nowIso)} сэрүүлэг тавилаа.`;
    case "create_calendar_event":
      return `За, ${formatWhenMn(action.arguments.start_at, nowIso)} календарьт нэмлээ.`;
    case "send_message":
      return `За, ${toward(action.arguments.contact_name)} мессеж явууллаа.`;
    case "create_note":
      return "За, тэмдэглэчихлээ.";
    default:
      return MN.ui.success;
  }
}

function handedOffSentence(action: ActionRequest): string {
  switch (action.tool) {
    case "call_contact":
      return `За, ${toward(action.arguments.contact_name)} тань залгаж байна.`;
    case "open_maps": {
      const how = TRAVEL_MN[action.arguments.mode] ?? "";
      return `За, ${toward(action.arguments.destination)} ${how}замыг газрын зураг дээр нээлээ.`;
    }
    default:
      return "За, нээчихлээ.";
  }
}

const TRAVEL_MN: Partial<Record<string, string>> = {
  transit: "автобусаар очих ",
  walking: "алхаж очих ",
};

/** Same wording as the backend's compose.py. */
function stopsSentence(stops: unknown): string {
  const named = (Array.isArray(stops) ? stops : []).filter(
    (s): s is { name: string; distance_m?: number } =>
      typeof s === "object" && s !== null && typeof (s as { name?: unknown }).name === "string",
  );
  const [first, ...rest] = named;
  if (!first) return "Ойролцоо автобусны буудал олдсонгүй.";
  const metres = (s: { distance_m?: number }) => Math.max(10, Math.round((s.distance_m ?? 0) / 10) * 10);
  let sentence = `Хамгийн ойрын буудал ${first.name}, ${metres(first)} метрийн зайтай.`;
  if (rest.length > 0) {
    sentence += ` Дараа нь ${rest
      .slice(0, 2)
      .map((s) => `${s.name} ${metres(s)} метр`)
      .join(", ")}.`;
  }
  return `${sentence} Газрын зураг дээр харууллаа.`;
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
