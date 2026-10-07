"""Final Mongolian answer composed from REAL action outcomes.

Deterministic on purpose: the words "хийчихлээ", "тавилаа" etc. appear only when the
matching result status says so. Partial failures are reported per action.
"""

from __future__ import annotations

from datetime import date

from .models import ActionRequest, ActionResult

MN_PERMISSION_DENIED = "Энэ үйлдлийг хийхийн тулд утасныхаа тохиргооноос зөвшөөрөл өгөх хэрэгтэй байна."
MN_PHONE_UNAVAILABLE = "Уучлаарай, утсан дээр энэ үйлдлийг одоохондоо хийж чадахгүй байна."

# (verb form, dative form) — vowel harmony spelled out.
ACTION_MN: dict[str, tuple[str, str]] = {
    "call_contact": ("залгах", "залгахад"),
    "send_message": ("мессеж бичих", "мессеж бичихэд"),
    "create_reminder": ("сануулга үүсгэх", "сануулга үүсгэхэд"),
    "create_calendar_event": ("календарьт нэмэх", "календарьт нэмэхэд"),
    "create_alarm": ("сэрүүлэг тавих", "сэрүүлэг тавихад"),
    "create_note": ("тэмдэглэл хадгалах", "тэмдэглэл хадгалахад"),
    "open_maps": ("газрын зураг нээх", "газрын зураг нээхэд"),
    "get_weather": ("цаг агаар харах", "цаг агаар харахад"),
    "web_search": ("хайлт хийх", "хайлт хийхэд"),
    "get_current_time": ("цаг харах", "цаг харахад"),
    "open_url": ("вэб хуудас нээх", "вэб хуудас нээхэд"),
    "open_app": ("програм нээх", "програм нээхэд"),
    "set_timer": ("таймер тавих", "таймер тавихад"),
    "list_reminders": ("сануулгуудыг харах", "сануулгуудыг харахад"),
    "cancel_reminder": ("сануулга цуцлах", "сануулга цуцлахад"),
    "computer_control": ("компьютер удирдах", "компьютер удирдахад"),
}

FOLDER_NAMES = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}
KIND_MN = {"reminder": "сануулга", "alarm": "сэрүүлэг", "timer": "таймер", "event": "уулзалт"}

UNSUPPORTED_BY_CODE = {
    "WEB_NO_IPHONE_ACTIONS": "Компьютерийн browser дээр {verb} боломжгүй. Үүнийг iPhone дээр туршина.",
    "EXPO_GO_NATIVE_UNAVAILABLE": "Expo Go дээр {verb} боломжгүй. Үүнд development build хэрэгтэй.",
    "NATIVE_MODULE_NOT_BUILT": "{Verb} үйлдэл одоохондоо бэлэн болоогүй байна.",
    "SMS_UNAVAILABLE": "Энэ утсаар мессеж илгээх боломжгүй байна.",
    "IOS_CANNOT_OPEN_APPS": "iPhone дээр Duud өөр апп нээж чадахгүй, iOS үүнийг зөвшөөрдөггүй.",
    "IOS_NO_SYSTEM_CONTROL": "iPhone дээр Duud дууны түвшин өөрчлөх, утсыг түгжих боломжгүй, iOS зөвшөөрдөггүй.",
    # Possible on Android, but not from Expo Go: these need a native build of Duud.
    "ANDROID_CANNOT_OPEN_APPS": "Android утсан дээр Duud одоохондоо өөр апп нээж чадахгүй.",
    "ANDROID_NO_SYSTEM_CONTROL": "Android утсан дээр Duud одоохондоо дууны түвшин өөрчлөх, утсыг түгжих боломжгүй.",
}

PERMISSION_BY_CODE = {
    "CONTACTS_DENIED": "Контакт харах зөвшөөрөл хэрэгтэй байна. Утасныхаа Settings-ээс Expo Go-д Contacts зөвшөөрөл өгнө үү.",
    "NOTIFICATIONS_DENIED": "Мэдэгдэл илгээх зөвшөөрөл хэрэгтэй байна. Утасныхаа Settings-ээс Expo Go-д Notifications зөвшөөрөл өгнө үү.",
}

FAILED_BY_CODE = {
    "WEB_SEARCH_NOT_CONFIGURED": "Вэб хайлт холбогдоогүй байна. apps/api/.env-д TAVILY_API_KEY нэмнэ үү.",
    "WEB_SEARCH_UNAVAILABLE": "Вэб хайлт хийх эрх алга байна. Gemini key-д төлбөр (billing) холбох хэрэгтэй.",
    "WEB_SEARCH_KEY_INVALID": "Tavily API key буруу байна (apps/api/.env).",
    "WEB_SEARCH_LIMIT": "Энэ сарын үнэгүй хайлтын эрх (Tavily, 1000 удаа) дууссан байна.",
    "WEB_SEARCH_FAILED": "Вэбээс хайхад асуудал гарлаа.",
    "APP_NOT_FOUND": "'{app}' гэсэн програм энэ компьютер дээр олдсонгүй.",
    "URL_NOT_HTTP": "Энэ хаягийг нээж чадсангүй.",
    "LOCATION_NOT_FOUND": "Тэр газрыг олсонгүй. Өөрөөр хэлээд өгөөч.",
    "CONTACT_NOT_FOUND": "{name} гэсэн контакт олдсонгүй.",
    "CONTACT_NO_PHONE": "{name} гэсэн контактад утасны дугаар алга.",
    "TIME_IN_PAST": "Тэр цаг аль хэдийн өнгөрсөн байна. Өөр цаг хэлээд өгөөч.",
    "REMINDER_NOT_FOUND": "Тийм сануулга олдсонгүй.",
    "VOLUME_UNAVAILABLE": "Компьютерын дууны төхөөрөмж олдсонгүй.",
}


BACK_VOWELS = set("аоуяёы")
FRONT_VOWELS = set("эөүе")


def toward(phrase: str) -> str:
    """Directional case "руу/рүү/луу/лүү" by vowel harmony of the last word:
    "Бат руу", "Ээж рүү", "Баатар луу", "Сүхбаатарын талбай руу"."""
    word = (phrase.strip().split() or [""])[-1].lower()
    if any(c in BACK_VOWELS for c in word):
        back = True
    elif any(c in FRONT_VOWELS or c == "и" for c in word):
        back = False  # front vowels, or only the neutral "и" ("Билгүүн", "Өлзий")
    else:
        back = True  # no vowels (abbreviations)
    stem = "л" if word.endswith("р") else "р"
    return f"{phrase} {stem}{'уу' if back else 'үү'}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def format_when_mn(iso: str, now_iso: str) -> str:
    """"маргааш өглөө 9 цагт", "өнөөдөр орой 7:30-д" — read from the ISO string as written."""
    d = date.fromisoformat(iso[:10])
    h, m = int(iso[11:13]), int(iso[14:16])
    diff = (d - date.fromisoformat(now_iso[:10])).days
    day = {0: "өнөөдөр", 1: "маргааш", 2: "нөгөөдөр"}.get(diff, f"{d.month} сарын {d.day}-нд")
    part = "шөнө" if h < 5 else "өглөө" if h < 12 else "өдөр" if h < 18 else "орой" if h < 23 else "шөнө"
    h12 = 12 if h % 12 == 0 else h % 12
    clock = f"{h12} цагт" if m == 0 else f"{h12}:{m:02d}-д"
    return f"{day} {part} {clock}"


def duration_mn(seconds: int) -> str:
    """600 -> "10 минутын", 5400 -> "1 цаг 30 минутын", 45 -> "45 секундын" (genitive, before "таймер")."""
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [(h, "цаг", "цагийн"), (m, "минут", "минутын"), (s, "секунд", "секундын")]
    used = [(n, plain, gen) for n, plain, gen in parts if n]
    return " ".join(f"{n} {gen if i == len(used) - 1 else plain}" for i, (n, plain, gen) in enumerate(used))


def _scheduled_list(items: list[dict], now_iso: str) -> str:
    if not items:
        return "Одоогоор товлосон сануулга, сэрүүлэг алга байна."
    lines = [f"{format_when_mn(i['fire_at'], now_iso)} {i.get('title') or KIND_MN.get(i.get('kind', ''), 'сануулга')}" for i in items[:5]]
    more = f", бас {len(items) - 5} нь" if len(items) > 5 else ""
    return f"Танд {len(items)} зүйл товлогдсон байна: " + ", ".join(lines) + more + "."


def _computer_sentence(a: dict, data: dict) -> str:
    level = data.get("volume")
    now = f" Одоо {level}% байна." if isinstance(level, int) else ""
    match a.get("action"):
        case "volume_up":
            return "За, дууг нэмлээ." + now
        case "volume_down":
            return "За, дууг багасгалаа." + now
        case "set_volume":
            return f"За, дууг {a.get('level', level)}% болголоо."
        case "mute":
            return "За, дууг хаалаа."
        case "unmute":
            return "За, дууг нээлээ." + now
        case "lock_screen":
            return "За, компьютерээ түгжлээ."
        case "open_folder":
            return f"За, {FOLDER_NAMES.get(a.get('folder', ''), 'хавтсыг')} хавтсыг нээлээ."
    return "За, хийчихлээ."


def sentence_for(action: ActionRequest, r: ActionResult, now_iso: str) -> str:
    verb, dative = ACTION_MN[action.tool]
    a = action.arguments
    if r.status == "succeeded":
        if r.data and r.data.get("summary_mn"):
            return str(r.data["summary_mn"])
        data = r.data or {}
        match action.tool:
            case "set_timer":
                where = (
                    " Компьютер дээр дуугарна." if r.executed_via == "backend"
                    else " Утас чимээгүй горимд байвал дуугарахгүй шүү."
                )
                return f"За, {duration_mn(int(a['duration_seconds']))} таймер тавилаа." + where
            case "list_reminders":
                return _scheduled_list(list(data.get("items") or []), now_iso)
            case "cancel_reminder":
                cancelled = [str(t) for t in (data.get("cancelled") or [])]
                return f"За, {', '.join(cancelled)} цуцаллаа." if cancelled else "За, цуцаллаа."
            case "computer_control":
                return _computer_sentence(a, data)
        if r.executed_via == "backend":
            # Done on the Windows PC (desktop.py): toasts while Duud runs, notes in a file.
            match action.tool:
                case "create_reminder":
                    return f"За, {format_when_mn(a['due_at'], now_iso)} компьютер дээр мэдэгдлээр сануулъя."
                case "create_alarm":
                    return f"За, {format_when_mn(a['fire_at'], now_iso)} компьютер дээр сэрүүлэг дуугаргана. Duud асаалттай байх хэрэгтэй."
                case "create_calendar_event":
                    return f"Календарьт шууд нэмж чадахгүй ч {format_when_mn(a['start_at'], now_iso)} компьютер дээр мэдэгдлээр сануулъя."
                case "create_note":
                    return "За, тэмдэглэчихлээ. Documents доторх 'Duud тэмдэглэл.txt' файлд байгаа."
                case "open_app":
                    return f"За, {a['app_name']} нээлээ."
        if r.executed_via == "react_native":
            # Expo Go has no Clock or Calendar access: these are local notifications. Say so.
            match action.tool:
                case "create_alarm":
                    return (
                        f"За, {format_when_mn(a['fire_at'], now_iso)} мэдэгдлээр сэрээнэ. "
                        "Утас чимээгүй горимд байвал дуугарахгүй шүү."
                    )
                case "create_calendar_event":
                    return f"Календарьт шууд нэмж чадахгүй ч {format_when_mn(a['start_at'], now_iso)} мэдэгдлээр сануулъя."
        match action.tool:
            case "create_reminder":
                return f"За, {format_when_mn(a['due_at'], now_iso)} сануулъя."
            case "create_alarm":
                return f"За, {format_when_mn(a['fire_at'], now_iso)} сэрүүлэг тавилаа."
            case "create_calendar_event":
                return f"За, {format_when_mn(a['start_at'], now_iso)} календарьт нэмлээ."
            case "send_message":
                return f"За, {toward(a['contact_name'])} мессеж явууллаа."
            case "create_note":
                return "За, тэмдэглэчихлээ."
        return "За, хийчихлээ."
    if r.status == "handed_off":
        match action.tool:
            case "call_contact":
                return f"За, {toward(a['contact_name'])} тань залгаж байна."
            case "open_maps":
                return f"За, {toward(a['destination'])} замыг газрын зураг дээр нээлээ."
            case "send_message":
                return f"За, {toward(a['contact_name'])} бичих мессежийг бэлдлээ. Илгээх товчийг дараарай."
            case "open_url":
                return f"За, {a.get('title') or 'хуудсыг'} нээлээ."
        return "За, нээчихлээ."
    if r.status == "cancelled":
        return "За, болиулчихлаа."
    if r.status == "permission_denied":
        return PERMISSION_BY_CODE.get(r.error_code or "", MN_PERMISSION_DENIED)
    if r.status == "needs_clarification":
        if action.tool == "cancel_reminder" and r.match_count:
            return f"{r.match_count} зүйл товлогдсон байна. Алийг нь цуцлахаа нэр эсвэл цагаар нь хэлээрэй."
        if r.match_count and a.get("contact_name"):
            return f"{a['contact_name']} гэсэн {r.match_count} контакт байна. Аль нь болохыг бүтэн нэрээр нь хэлээд өгөөч."
        return "Аль нь болохыг тодруулаад өгөөч."
    if r.status == "unsupported":
        template = UNSUPPORTED_BY_CODE.get(r.error_code or "")
        return template.format(verb=verb, Verb=_cap(verb)) if template else MN_PHONE_UNAVAILABLE
    template = FAILED_BY_CODE.get(r.error_code or "")
    if not template:
        return f"{_cap(dative)} асуудал гарлаа."
    return template.format(name=a.get("contact_name", ""), app=a.get("app_name", ""))


def compose(actions: list[ActionRequest], results: list[ActionResult], now_iso: str) -> str:
    by_id = {a.id: a for a in actions}
    parts = [sentence_for(by_id[r.action_id], r, now_iso) for r in results if r.action_id in by_id]
    # Collapse repeated identical sentences (e.g. several "болиулчихлаа").
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return " ".join(seen)
