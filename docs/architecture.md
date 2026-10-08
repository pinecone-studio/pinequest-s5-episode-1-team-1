# BEKHI architecture

## The one rule

**The backend decides WHAT should happen. The iPhone decides HOW, and is the only
thing that can say whether it happened.**

The backend never performs iPhone actions and never claims a device action
succeeded. Device outcomes come back only from `POST /api/v1/assistant/actions/results`.

## Turn lifecycle

```
 iPhone                                   FastAPI
 ──────                                   ───────
 record audio ──multipart(audio,context)──▶ POST /assistant/voice
                                           STT → transcript (mn)          ── apps/speech (BuzzASR)
                                           LLM planner → tool calls       ── Gemini
                                           validate args (contracts schemas)
                                           run backend tools (weather, time, search)
                                           persist turn + pending tool_calls
            ◀──────── AssistantTurn ─────── stage = final | awaiting_confirmation
                                                    | awaiting_device | awaiting_clarification
 validate AssistantTurn (zod) — reject malformed turns
 if awaiting_confirmation: show/speak prompt, wait for Тийм/Үгүй
 for each device action, in order:
   IOSActionService.execute(action)
     → strategy[0..n] (EventKit / AlarmKit / tel: / Maps URL / Shortcut)
     → ActionResult (succeeded | handed_off | cancelled | permission_denied
                     | unsupported | needs_clarification | failed)
 POST /assistant/actions/results ─────────▶ persist results
                                           compose final Mongolian answer from REAL outcomes
                                           TTS                            ── apps/speech (OronTTS)
            ◀──── ActionResultsResponse ─── "7 цагийн сэрүүлгийг тохирууллаа. Харин 8:30-ийн…"
 play audio, show text
```

Turns with only backend tools (weather, time, search) finish in one round trip
with `stage: "final"`.

## Decisions

| # | Decision | Why |
|---|----------|-----|
| D1 | `packages/contracts` (zod) is the wire contract. The app validates every backend response at runtime before acting. | The app must never execute a malformed action. One definition gives TS types plus runtime validation. |
| D2 | `contracts/generated/*.json` (JSON Schema + tool manifest) is exported from zod and committed. The FastAPI Pydantic models are contract-tested against it, and so are the shared `examples/`. | Python and TS can't share code. Shared schemas and examples catch drift in CI without a codegen chain. |
| D3 | The backend turns all dates and times into absolute ISO-8601 with an offset (`2026-10-07T09:00:00+08:00`), resolved against `client_now` + `timezone`. | Swift should never parse "маргааш". It also makes "маргааш" carry-over across turns a backend memory problem, which is testable. |
| D4 | Contact names are normalized to the nominative case by the LLM ("Ээж рүүгээ" → "Ээж") and resolved **on the device**. Ambiguity is asked about on the device. Only `match_count` is reported. | Contact data never leaves the phone. |
| D5 | The extra endpoint `POST /api/v1/assistant/actions/results` was added on top of the spec's list. | It's the only honest way to produce the final spoken answer, including partial failures. |
| D6 | `handed_off` is a separate status from `succeeded`. | With `tel:`, Maps or Shortcuts the app opens system UI and can't observe the result. Wording: "залгаж байна", not "залгалаа". |
| D7 | Confirmation happens on the device, from `confirmation.prompt`. The app does not execute until the user answers yes. A "no" is reported as `cancelled`. | Calls and messages always need confirmation (tool manifest). |
| D8 | STT, LLM and TTS sit behind provider interfaces in the backend (`providers/stt`, `providers/llm`, `providers/tts`). Defaults: **BuzzASR** STT, **Gemini** LLM, **OronTTS** TTS. See [speech-models.md](speech-models.md). | Mongolian quality varies a lot by provider. Implementations can be swapped without touching the pipeline. |
| D9 | STT and TTS run in a separate GPU service, `apps/speech`, which only `apps/api` calls (bearer token). | Both models need a GPU. Railway/Render have none. The API stays cheap and CPU-only. |
| D10 | The iPhone records 16 kHz mono 16-bit WAV (`AUDIO_UPLOAD`), max 30 s. | That's BuzzASR's native input, so there's no server-side transcoding or ffmpeg. |
| D11 | TTS voice is `female` or `male` only (`TtsVoice`). Reference audio is never accepted from clients. | F5-TTS clones any reference voice. Allowing uploads would turn BEKHI into a voice-cloning service. |
| D12 | Alarms and timers with `target: "all"` (the default) go to every device linked with the same **sync code** (`packages/contracts/src/sync.ts`, `apps/api` `sync.py`). The backend sets `sync_id` and a timer's `fire_at` from its own clock. The device that heard the command schedules its copy, then publishes it. The other devices pull the list and schedule their own copies **ahead of time**. Cancelling marks it cancelled for every device. The server stores only the SHA-256 of the code (Supabase `sync_alarms`/`sync_devices`, or in memory when Supabase is not configured). | A device rings even if the network is down at that moment: it only has to be online once after the alarm was set. Linking needs no login screen, and Supabase Auth can replace the code later behind the same endpoints. Replies say "илгээлээ" (sent), not "тавилаа" (set), for the other devices, because the server cannot see whether they have scheduled their copies yet. |

## Repository layout

```
bekhi/
├── apps/
│   ├── mobile/          Expo (dev build) + Expo Router + Zustand; Swift in modules/bekhi-ios-actions (Phase 2, 9)
│   ├── api/             FastAPI + Pydantic + uv, CPU only — Railway/Render (Phase 3)
│   └── speech/          GPU service: BuzzASR STT + OronTTS (Phase 5, 16)
├── packages/
│   └── contracts/       wire contract, tool manifest, examples, intent fixtures
├── supabase/
│   └── migrations/      SQL + RLS (Phase 8)
└── docs/
```

## Mobile layering (Phase 2 / 9)

```
screens (Expo Router)  ──▶  useAssistantStore (Zustand)  ──▶  AssistantClient (HTTP, validates with contracts)
                                         │
                                         ▼
                              IOSActionService (TS interface, platform-free)
                                         │  callContact / createReminder / createCalendarEvent
                                         │  createAlarm / createNotification / openMaps / executeShortcut
                                         ▼
                      Expo native module "BekhiIOSActions" (Swift, isolated)
                                         ▼
                 EventKit · Contacts · AlarmKit · UserNotifications · MessageUI · UIApplication.open
```

App Intents (Phase 14) live in the **main app target**. A config plugin copies them in at
prebuild time, because App Intents metadata is not extracted from static CocoaPods libraries.
They call the same Swift action layer, so Shortcuts and the in-app assistant share one implementation.
