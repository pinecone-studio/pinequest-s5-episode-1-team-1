"""Final Mongolian answer composed from REAL action outcomes.

Deterministic on purpose: the words "хийчихлээ", "тавилаа" etc. appear only when the
matching result status says so. Partial failures are reported per action.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from .models import ActionRequest, ActionResult

# The app's name: BEKHI in Latin letters, БЭХИ in Mongolian text. Written in capitals the speech
# synthesizer spells it out letter by letter, so speech gets it as an ordinary word.
APP_NAME = "БЭХИ"
SPOKEN_APP_NAME = "Бэхи"

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
    "add_todo": ("жагсаалтад нэмэх", "жагсаалтад нэмэхэд"),
    "list_todos": ("жагсаалт харах", "жагсаалт харахад"),
    "complete_todo": ("тэмдэглэх", "тэмдэглэхэд"),
    "delete_todo": ("устгах", "устгахад"),
    "open_url": ("вэб хуудас нээх", "вэб хуудас нээхэд"),
    "open_app": ("апп нээх", "апп нээхэд"),
    "set_timer": ("таймер тавих", "таймер тавихад"),
    "list_reminders": ("сануулгуудыг харах", "сануулгуудыг харахад"),
    "cancel_reminder": ("сануулга цуцлах", "сануулга цуцлахад"),
    "computer_control": ("компьютер удирдах", "компьютер удирдахад"),
    "daily_briefing": ("өдрийн тойм гаргах", "өдрийн тойм гаргахад"),
    "create_routine": ("өдөр бүрийн тойм тохируулах", "өдөр бүрийн тойм тохируулахад"),
    "remember": ("санах", "санахад"),
    "forget": ("мартах", "мартахад"),
}

FOLDER_NAMES = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}
KIND_MN = {"reminder": "сануулга", "alarm": "сэрүүлэг", "timer": "таймер", "event": "уулзалт", "routine": "өдрийн тойм"}
DEVICE_MN = {"ios": "iPhone", "android": "Android утас", "web": "компьютер"}
MN_SYNC_FAILED = "Бусад төхөөрөмж рүү илгээж чадсангүй, зөвхөн энд тавигдлаа."
MN_SYNC_CANCEL_FAILED = "Гэхдээ бусад төхөөрөмж дээр цуцалж чадсангүй."

UNSUPPORTED_BY_CODE = {
    "WEB_NO_IPHONE_ACTIONS": "Компьютерийн browser дээр {verb} боломжгүй. Үүнийг iPhone дээр туршина.",
    "EXPO_GO_NATIVE_UNAVAILABLE": "Expo Go дээр {verb} боломжгүй. Үүнд development build хэрэгтэй.",
    "NATIVE_MODULE_NOT_BUILT": "{Verb} үйлдэл одоохондоо бэлэн болоогүй байна.",
    "SMS_UNAVAILABLE": "Энэ утсаар мессеж илгээх боломжгүй байна.",
    "IOS_CANNOT_OPEN_APPS": "iPhone дээр '{app}' аппыг нээж чадсангүй. iOS зөвхөн YouTube, Spotify, Facebook шиг "
    "танил аппуудыг нээхийг зөвшөөрдөг.",
    "IOS_NO_SYSTEM_CONTROL": "iPhone дээр БЭХИ дууны түвшин өөрчлөх, утсыг түгжих боломжгүй, iOS зөвшөөрдөггүй.",
    # Possible on Android, but not from Expo Go: these need a native build of BEKHI.
    "ANDROID_CANNOT_OPEN_APPS": "Expo Go дээр '{app}' аппыг нээж чадсангүй. БЭХИ-гийн Android апп суулгавал утсан "
    "дээрх ямар ч аппыг нэрээр нь нээнэ.",
    "ANDROID_NO_SYSTEM_CONTROL": "Android утсан дээр БЭХИ одоохондоо дууны түвшин өөрчлөх, утсыг түгжих боломжгүй.",
    # The cloud web app on a PC without BEKHI's PC agent running (apps/api agent.py).
    "DESKTOP_AGENT_OFF": "Компьютер дээр {verb} боломжгүй байна: энэ компьютерт БЭХИ агент асаагүй байна.",
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
    "APP_NOT_INSTALLED": "'{app}' гэсэн апп энэ утсанд олдсонгүй.",
    "APP_OPEN_FAILED": "'{app}' аппыг нээж чадсангүй.",
    "URL_NOT_HTTP": "Энэ хаягийг нээж чадсангүй.",
    "LOCATION_NOT_FOUND": "Тэр газрыг олсонгүй. Өөрөөр хэлээд өгөөч.",
    "CONTACT_NOT_FOUND": "{name} гэсэн контакт олдсонгүй.",
    "CONTACT_NO_PHONE": "{name} гэсэн контактад утасны дугаар алга.",
    "TIME_IN_PAST": "Тэр цаг аль хэдийн өнгөрсөн байна. Өөр цаг хэлээд өгөөч.",
    "TODO_NOT_FOUND": "Жагсаалтаас тийм зүйл олдсонгүй.",
    "TODO_AMBIGUOUS": "Жагсаалтад хэд хэдэн ийм зүйл байна. Аль нь болохыг нэрээр нь тодорхой хэлээрэй.",
    "TODO_FULL": "Жагсаалт дүүрсэн байна. Заримыг нь устгана уу.",
    "TODO_UNAVAILABLE": "Жагсаалт руу одоо хандаж чадсангүй. Түр хүлээгээд дахин хэлээрэй.",
    "MEMORY_FULL": "Санах зүйл дүүрсэн байна. Заримыг нь мартуулаарай.",
    "MEMORY_NOT_FOUND": "Тийм зүйл санаагүй байна.",
    "MEMORY_UNAVAILABLE": "Санах ой руу одоо хандаж чадсангүй. Түр хүлээгээд дахин хэлээрэй.",
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


def clock_mn(hhmm: str) -> str:
    """"07:00" -> "өглөө 7 цагт", "21:30" -> "орой 9:30-д" (a time of day, no date)."""
    day = "2000-01-01"
    return format_when_mn(f"{day}T{hhmm}:00+00:00", f"{day}T00:00:00+00:00").removeprefix("өнөөдөр ")


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


def _app_sentence(a: dict, data: dict) -> str:
    """The app the phone (or a browser tab) opened, named as the device reports it, and the search done there."""
    app = str(data.get("app") or a["app_name"])
    query = a.get("query")
    if query and data.get("searched"):
        return f"За, {app} дээр '{query}' гэж хайлаа."
    if query:
        return f"За, {app} нээлээ. '{query}' гэж тэндээсээ хайгаарай."
    return f"За, {app} нээлээ."


def sync_note(data: dict | None) -> str:
    """Where else a synced alarm/timer went, as reported by the device that published it.
    "Sent", not "set": each device schedules its copy once it is online."""
    sync = (data or {}).get("sync")
    if not isinstance(sync, dict):
        return ""  # target "this", or no devices linked
    if sync.get("status") != "sent":
        return MN_SYNC_FAILED
    counts = Counter(DEVICE_MN.get(str(p), "төхөөрөмж") for p in sync.get("other_devices") or [])
    if not counts:
        return ""  # only this device is linked
    names = ", ".join(name if n == 1 else f"{n} {name}" for name, n in counts.items())
    return f"Бусад төхөөрөмж рүү бас илгээлээ: {names}."


def sentence_for(action: ActionRequest, r: ActionResult, now_iso: str) -> str:
    sentence = _sentence(action, r, now_iso)
    if action.tool in ("create_alarm", "set_timer") and r.status == "succeeded":
        sentence = f"{sentence} {sync_note(r.data)}".strip()
    if action.tool == "cancel_reminder" and ((r.data or {}).get("sync") or {}).get("status") == "failed":
        sentence = f"{sentence} {MN_SYNC_CANCEL_FAILED}"
    return sentence


def _sentence(action: ActionRequest, r: ActionResult, now_iso: str) -> str:
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
            case "create_routine":
                return (
                    f"За, өдөр бүр {clock_mn(a['time'])} өдрийн тоймын мэдэгдэл ирнэ. "
                    "Дарахад нь цаг агаар, хийх зүйлсийг тань хэлж өгье."
                )
        if r.executed_via == "backend":
            # Done on the Windows PC (desktop.py): toasts while BEKHI runs, notes in a file.
            match action.tool:
                case "create_reminder":
                    return f"За, {format_when_mn(a['due_at'], now_iso)} компьютер дээр мэдэгдлээр сануулъя."
                case "create_alarm":
                    return f"За, {format_when_mn(a['fire_at'], now_iso)} компьютер дээр сэрүүлэг дуугаргана. БЭХИ асаалттай байх хэрэгтэй."
                case "create_calendar_event":
                    return f"Календарьт шууд нэмж чадахгүй ч {format_when_mn(a['start_at'], now_iso)} компьютер дээр мэдэгдлээр сануулъя."
                case "create_note":
                    return "За, тэмдэглэчихлээ. Documents доторх 'БЭХИ тэмдэглэл.txt' файлд байгаа."
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
            case "open_app":
                return _app_sentence(a, r.data or {})
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
        return template.format(verb=verb, Verb=_cap(verb), app=a.get("app_name", "")) if template else MN_PHONE_UNAVAILABLE
    template = FAILED_BY_CODE.get(r.error_code or "")
    if not template:
        return f"{_cap(dative)} асуудал гарлаа."
    return template.format(name=a.get("contact_name", ""), app=a.get("app_name", ""))


def _today_schedule(r: ActionResult, now_iso: str) -> str:
    """In the day's briefing: only what the device has scheduled today, and nothing when it
    cannot list them (a browser without the PC's API)."""
    if r.status != "succeeded":
        return ""
    today = now_iso[:10]
    items = [i for i in (r.data or {}).get("items") or [] if str(i.get("fire_at", ""))[:10] == today]
    if not items:
        return ""
    lines = [
        f"{format_when_mn(i['fire_at'], now_iso).removeprefix('өнөөдөр ')} "
        f"{i.get('title') or KIND_MN.get(i.get('kind', ''), 'сануулга')}"
        for i in items[:5]
    ]
    return "Өнөөдөр товлосон: " + ", ".join(lines) + "."


def compose(actions: list[ActionRequest], results: list[ActionResult], now_iso: str) -> str:
    by_id = {a.id: a for a in actions}
    briefing = any(a.tool == "daily_briefing" for a in actions)
    parts = [
        _today_schedule(r, now_iso) if briefing and by_id[r.action_id].tool == "list_reminders"
        else sentence_for(by_id[r.action_id], r, now_iso)
        for r in results
        if r.action_id in by_id
    ]
    # Collapse repeated identical sentences (e.g. several "болиулчихлаа").
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return " ".join(seen)


def speakable(text: str) -> str:
    """Text for the speech synthesizer: the app's name as a word it pronounces."""
    return re.sub(rf"\b{APP_NAME}\b", SPOKEN_APP_NAME, text)
