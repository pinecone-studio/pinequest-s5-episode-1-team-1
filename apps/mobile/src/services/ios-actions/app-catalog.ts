import { nameKeys, similarity } from "./name-match";

/**
 * One way to reach an app, tried in order until one opens:
 * - a URL: the app's own scheme or an https link. Phones open the app when it is installed and
 *   claims the link, else the browser; a browser uses only the https ones.
 * - { ios }: a URL only an iPhone understands.
 * - { android }: the installed Android app with this package name.
 * - { intent }: an Android system screen (camera, settings), or the default app of a category.
 */
export type AppTarget = string | { ios: string } | { android: string } | { intent: string; category?: string };

export interface CatalogApp {
  /** As the reply names it. */
  name: string;
  /** Other names people say, in any script. */
  aliases?: string[];
  open: AppTarget[];
  /** Search inside the app: URLs where {q} is the URL-encoded query, tried in order. */
  search?: (string | { ios: string })[];
}

const MAIN = "android.intent.action.MAIN";

/**
 * Apps people ask for by name, with the links they publish. Any other app is found by its name
 * among the apps installed on an Android phone (BekhiLauncher); iOS allows only these.
 */
export const APP_CATALOG: readonly CatalogApp[] = [
  {
    name: "YouTube",
    aliases: ["ютуб", "ютүб", "ютюб"],
    open: [{ android: "com.google.android.youtube" }, { ios: "youtube://" }, "https://www.youtube.com/"],
    search: ["https://www.youtube.com/results?search_query={q}"],
  },
  {
    name: "YouTube Music",
    aliases: ["ютуб мюзик"],
    open: [{ android: "com.google.android.apps.youtube.music" }, { ios: "youtubemusic://" }, "https://music.youtube.com/"],
    search: ["https://music.youtube.com/search?q={q}"],
  },
  {
    name: "Spotify",
    aliases: ["спотифай", "спотифи"],
    open: [{ android: "com.spotify.music" }, "spotify://", "https://open.spotify.com/"],
    search: ["spotify:search:{q}", "https://open.spotify.com/search/{q}"],
  },
  {
    name: "Facebook",
    aliases: ["фэйсбүүк", "фейсбүүк", "фейсбук", "фэйсбук", "fb"],
    open: [{ android: "com.facebook.katana" }, { ios: "fb://" }, "https://www.facebook.com/"],
    search: ["https://www.facebook.com/search/top/?q={q}"],
  },
  {
    name: "Messenger",
    aliases: ["мессенжер", "мессенжэр", "facebook messenger"],
    open: [{ android: "com.facebook.orca" }, { ios: "fb-messenger://" }, "https://www.messenger.com/"],
  },
  {
    name: "Instagram",
    aliases: ["инстаграм", "инстаграмм", "insta"],
    open: [{ android: "com.instagram.android" }, { ios: "instagram://app" }, "https://www.instagram.com/"],
  },
  {
    name: "WhatsApp",
    aliases: ["вотсап", "ватсап", "вацап"],
    open: [{ android: "com.whatsapp" }, { ios: "whatsapp://" }, "https://web.whatsapp.com/"],
  },
  {
    name: "Telegram",
    aliases: ["телеграм", "телеграмм"],
    open: [{ android: "org.telegram.messenger" }, "tg://", "https://web.telegram.org/"],
  },
  {
    name: "Viber",
    aliases: ["вайбер"],
    open: [{ android: "com.viber.voip" }, "viber://", "https://www.viber.com/"],
  },
  {
    name: "TikTok",
    aliases: ["тикток", "тик ток"],
    open: [
      { android: "com.zhiliaoapp.musically" },
      { android: "com.ss.android.ugc.trill" },
      { ios: "snssdk1233://" },
      "https://www.tiktok.com/",
    ],
    search: ["https://www.tiktok.com/search?q={q}"],
  },
  {
    name: "X",
    aliases: ["twitter", "твиттер", "твитер"],
    open: [{ android: "com.twitter.android" }, { ios: "twitter://" }, "https://x.com/"],
    search: ["https://x.com/search?q={q}"],
  },
  {
    name: "Netflix",
    aliases: ["нетфликс"],
    open: [{ android: "com.netflix.mediaclient" }, { ios: "nflx://" }, "https://www.netflix.com/"],
    search: ["https://www.netflix.com/search?q={q}"],
  },
  {
    name: "Zoom",
    aliases: ["зоом", "зүүм"],
    open: [{ android: "us.zoom.videomeetings" }, { ios: "zoomus://" }, "https://zoom.us/"],
  },
  {
    name: "Gmail",
    aliases: ["жимэйл", "жимейл", "google mail"],
    open: [{ android: "com.google.android.gm" }, { ios: "googlegmail://" }, "https://mail.google.com/"],
    search: ["https://mail.google.com/mail/u/0/#search/{q}"],
  },
  {
    name: "Google Maps",
    aliases: ["гүүгл мапс", "google map"],
    open: [{ android: "com.google.android.apps.maps" }, { ios: "comgooglemaps://" }, "https://www.google.com/maps"],
    search: [{ ios: "comgooglemaps://?q={q}" }, "https://www.google.com/maps/search/?api=1&query={q}"],
  },
  {
    name: "Chrome",
    aliases: ["google chrome", "хром"],
    open: [{ android: "com.android.chrome" }, { ios: "googlechrome://" }, "https://www.google.com/"],
    search: [{ ios: "googlechrome://www.google.com/search?q={q}" }, "https://www.google.com/search?q={q}"],
  },
  {
    name: "Google",
    aliases: ["гүүгл"],
    open: [{ android: "com.google.android.googlequicksearchbox" }, "https://www.google.com/"],
    search: ["https://www.google.com/search?q={q}"],
  },
  {
    name: "Google Translate",
    aliases: ["translate", "орчуулагч", "гүүгл орчуулагч", "google орчуулагч"],
    open: [{ android: "com.google.android.apps.translate" }, { ios: "googletranslate://" }, "https://translate.google.com/"],
  },
  {
    name: "Google Drive",
    aliases: ["drive", "гүүгл драйв"],
    open: [{ android: "com.google.android.apps.docs" }, { ios: "googledrive://" }, "https://drive.google.com/"],
  },
  {
    name: "Google Photos",
    aliases: ["гүүгл фото"],
    open: [{ android: "com.google.android.apps.photos" }, { ios: "googlephotos://" }, "https://photos.google.com/"],
  },
  {
    name: "Play Store",
    aliases: ["google play", "плей стор", "плэй стор"],
    open: [{ android: "com.android.vending" }],
    search: ["market://search?q={q}&c=apps"],
  },
  {
    name: "App Store",
    aliases: ["апп стор", "эпп стор"],
    open: [{ ios: "itms-apps://apps.apple.com/" }, { android: "com.android.vending" }],
  },
  // The phone's own apps.
  {
    name: "Камер",
    aliases: ["camera", "камера", "зураг авах"],
    open: [{ intent: "android.media.action.STILL_IMAGE_CAMERA" }],
  },
  {
    name: "Зургийн цомог",
    aliases: ["gallery", "photos", "галерей", "зургууд"],
    open: [{ ios: "photos-redirect://" }, { intent: MAIN, category: "android.intent.category.APP_GALLERY" }],
  },
  {
    name: "Тохиргоо",
    aliases: ["settings", "сеттинг", "тохиргоонууд"],
    open: [{ intent: "android.settings.SETTINGS" }, { ios: "app-settings:" }],
  },
  {
    name: "Wi-Fi тохиргоо",
    aliases: ["wifi", "wi-fi", "вайфай", "вай фай", "интернэт тохиргоо"],
    open: [{ intent: "android.settings.WIFI_SETTINGS" }],
  },
  {
    name: "Bluetooth тохиргоо",
    aliases: ["bluetooth", "блютүүс", "блютуз"],
    open: [{ intent: "android.settings.BLUETOOTH_SETTINGS" }],
  },
  {
    name: "Тооны машин",
    aliases: ["calculator", "калькулятор"],
    open: [{ intent: MAIN, category: "android.intent.category.APP_CALCULATOR" }],
  },
  {
    name: "Календарь",
    aliases: ["calendar", "хуанли", "календар"],
    open: [{ ios: "calshow://" }, { intent: MAIN, category: "android.intent.category.APP_CALENDAR" }],
  },
  {
    name: "Мессеж",
    aliases: ["messages", "sms", "мессежүүд"],
    open: [{ intent: MAIN, category: "android.intent.category.APP_MESSAGING" }, "sms:"],
  },
  {
    name: "Утас",
    aliases: ["phone", "dialer", "залгах апп"],
    open: [{ intent: "android.intent.action.DIAL" }],
  },
  {
    name: "Имэйл",
    aliases: ["mail", "email", "и-мэйл", "мэйл", "майл"],
    open: [{ ios: "message://" }, { intent: MAIN, category: "android.intent.category.APP_EMAIL" }],
  },
  {
    name: "Хөгжим",
    aliases: ["music", "apple music"],
    open: [{ ios: "music://" }, { intent: MAIN, category: "android.intent.category.APP_MUSIC" }],
  },
  {
    name: "Файлууд",
    aliases: ["files", "файл"],
    open: [{ ios: "shareddocuments://" }, { android: "com.google.android.apps.nbu.files" }],
  },
];

/** Words that only say "an app": "Khan Bank app", "YouTube апп". */
const APP_WORDS = new Set(["app", "апп", "аппликейшн", "application", "програм"].map((w) => nameKeys(w).join(" ")));

function keysOf(name: string): string[] {
  return nameKeys(name).filter((k) => !APP_WORDS.has(k));
}

/** Below this two words are different names ("Khan" and "Xac" stay apart). */
const SAME_WORD = 0.9;

/**
 * How well a name the user said matches an app's name, 0 to 1. Every word the user said must
 * match a word of the app's name, so "Khan Bank" never opens "Xac Bank" and "Google Drive"
 * never opens "Google"; extra words in the app's name ("Facebook Lite") cost a little.
 */
export function appNameScore(said: string, appName: string): number {
  const want = keysOf(said);
  const have = keysOf(appName);
  if (want.length === 0 || have.length === 0) return 0;
  if (want.join("") === have.join("")) return 1; // "SocialPay" = "Social Pay"
  let total = 0;
  for (const w of want) {
    const best = Math.max(...have.map((h) => similarity(w, h)));
    if (best < SAME_WORD) return 0;
    total += best;
  }
  return (total / want.length) * 0.97 ** Math.max(0, have.length - want.length);
}

/** The known app the user named, if any. */
export function findCatalogApp(said: string): CatalogApp | null {
  let found: CatalogApp | null = null;
  let top = 0;
  for (const app of APP_CATALOG) {
    for (const name of [app.name, ...(app.aliases ?? [])]) {
      const score = appNameScore(said, name);
      if (score > top) {
        top = score;
        found = app;
      }
    }
  }
  return top >= SAME_WORD ? found : null;
}

/** Apps whose names match what the user said, best first. */
export function rankApps<T extends { label: string }>(apps: readonly T[], said: readonly string[]): T[] {
  return apps
    .map((app) => ({ app, score: Math.max(...said.map((s) => appNameScore(s, app.label))) }))
    .filter((x) => x.score >= SAME_WORD)
    .sort((x, y) => y.score - x.score)
    .map((x) => x.app);
}

/** A search link with the query filled in. */
export function fillQuery(template: string, query: string): string {
  return template.replace("{q}", encodeURIComponent(query));
}

const isWebsite = (t: unknown): t is string => typeof t === "string" && t.startsWith("https://");

/** What a browser opens for the app: its website, with the search there when it has one. */
export function appWebsite(app: CatalogApp, query?: string): { url: string; searched: boolean } | null {
  const search = query ? app.search?.find(isWebsite) : undefined;
  if (search && query) return { url: fillQuery(search, query), searched: true };
  const home = app.open.find(isWebsite);
  return home ? { url: home, searched: false } : null;
}
