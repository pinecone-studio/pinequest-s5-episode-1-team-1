# BEKHI

Mongolian voice-first personal assistant for iPhone (and Android, and the browser on your PC).

The user speaks Mongolian, casual and mixed with English. BEKHI works out the intent and runs
the action with **officially supported iOS APIs**, then replies in natural Mongolian, out loud.
It never claims an action succeeded unless the phone confirmed it.

> "Маргааш 7 цагт сэрээгээрэй" → an alarm for tomorrow 07:00 → "7 цагийн сэрүүлгийг тохирууллаа."

---

## Contents

1. [How it works](#how-it-works)
2. [Repository layout](#repository-layout)
3. [What you need](#what-you-need)
4. [First-time setup](#first-time-setup)
5. [Running the project](#running-the-project)
6. [Checking that it works](#checking-that-it-works)
7. [Everyday workflow](#everyday-workflow)
8. [Tests and checks](#tests-and-checks)
9. [Troubleshooting](#troubleshooting)
10. [Further reading](#further-reading)

---

## How it works

BEKHI has two parts that run at the same time:

| Part | Folder | What it does | Runs on |
|---|---|---|---|
| **Backend** | `apps/api` | Turns speech into text, decides what to do (Gemini), turns the answer into speech | Your PC, port **8000** |
| **App** | `apps/mobile` | Records your voice, shows and plays the reply, performs phone actions (alarms, calls, maps) | Phone (Expo Go) or browser, dev server on port **8081** |

One voice turn:

```
 Phone / browser                              Backend (apps/api)
 ───────────────                              ──────────────────
 tap the orb, speak
 16 kHz WAV ───────────────────────────────▶  speech → text        (Duudlaga, Gemini as fallback)
                                              text → plan          (Gemini: reply, weather, search, or a device action)
            ◀──────────── plan ─────────────
 run the device action (alarm, call, maps…)
 report what really happened ──────────────▶  write the final Mongolian answer from the real outcome
            ◀─────────── answer ────────────
 play the answer                ◀─────────── text → speech         (ElevenLabs, Gemini as fallback)
```

**The one rule:** the backend decides *what* should happen; the phone decides *how*, and is the
only thing that can say whether it happened. All AI keys stay on the backend; the app never sees them.

---

## Repository layout

```
apps/mobile         Expo SDK 57 · Expo Router · Zustand · TypeScript — the app
apps/api            Python 3.12 · FastAPI · uv · Gemini — the backend
apps/speech         GPU speech service (BuzzASR STT, OronTTS) — later phase, not needed to run
packages/contracts  The wire contract shared by app and backend (zod → JSON Schema), tool list, test fixtures
supabase            Database migrations — later phase, not needed to run
docs                Architecture, iOS capabilities, roadmap, speech models
```

This is an npm workspace: one `npm install` at the root installs `apps/mobile` and
`packages/contracts` together. The backend is a separate Python project managed by `uv`.

---

## What you need

### Tools

| Tool | Version | Check | Install |
|---|---|---|---|
| Node.js | 20.19 or newer | `node --version` | [nodejs.org](https://nodejs.org) |
| Python | 3.12 | `python --version` | `uv` installs it for you if it's missing |
| uv | any recent | `uv --version` | see below |
| Git | any | `git --version` | [git-scm.com](https://git-scm.com) |
| Expo Go (on the phone) | for SDK 57 | — | App Store / Google Play |

Install `uv`:

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Close and reopen your terminal afterwards**, otherwise `uv` is "not recognized".

### API keys

The backend needs these. They go in `apps/api/.env` only, never in the app.

| Key | Needed? | What for | Where to get it |
|---|---|---|---|
| `GEMINI_API_KEY` | **Required** | Understanding requests; fallback speech-to-text and text-to-speech | [Google AI Studio](https://aistudio.google.com/apikey) |
| `DUUDLAGA_API_KEY` | Recommended | Mongolian speech-to-text | [duudlaga.dev](https://duudlaga.dev) |
| `ELEVENLABS_API_KEY` | Recommended | Spoken replies (51 characters, starts with `sk_`) | [elevenlabs.io](https://elevenlabs.io) |
| `TAVILY_API_KEY` | Optional | Web search (1,000 free searches a month) | [tavily.com](https://tavily.com) |
| `GOOGLE_MAPS_API_KEY` | Optional | Directions on the in-app map (enable the **Routes API**) | [Google Cloud console](https://console.cloud.google.com/google/maps-apis) |

Weather (Open-Meteo) needs no key.

The map screen also draws Google Maps tiles, which use separate keys in `apps/mobile/.env`
(see `apps/mobile/.env.example`). In Expo Go on a phone, no tile key is needed. In the browser, set
`EXPO_PUBLIC_GOOGLE_MAPS_WEB_API_KEY` (Maps JavaScript API). For an APK or development build, set
`GOOGLE_MAPS_ANDROID_API_KEY` / `GOOGLE_MAPS_IOS_API_KEY`.

---

## First-time setup

Do this once after cloning, and again whenever someone renames or adds packages.

**1. Clone and install the app's packages**

```powershell
git clone https://github.com/pinecone-studio/pinequest-s5-episode-1-team-1.git
cd pinequest-s5-episode-1-team-1
npm install
```

**2. Install the backend's packages**

```powershell
cd apps/api
uv sync
```

This creates `apps/api/.venv` and installs Python 3.12 there if needed.

**3. Create the backend's secrets file**

```powershell
Copy-Item .env.example .env      # macOS / Linux: cp .env.example .env
```

Open `apps/api/.env` and paste your keys after the `=` signs (no quotes, no spaces). `.env` is
git-ignored, so it's never committed. Useful settings in that file:

- `STT_FALLBACK_PROVIDER=gemini` / `TTS_FALLBACK_PROVIDER=gemini`: keep talking when Duudlaga or
  ElevenLabs fails (no credits, bad key). Leave them empty to turn the fallback off.
- `ELEVENLABS_VOICE_ID`: the default voice "Ganbold" needs a **paid** ElevenLabs plan. On the free
  plan use a premade voice such as Adam, `pNInz6obpgDQGcFmaJgB`.
- `CORS_ORIGINS`: which web pages may call the API. The default, `http://localhost:8081`, is the
  Expo web app.

The app needs no `.env` for local development: it finds the backend by itself (see below).

---

## Running the project

Open **two terminals**: one for the backend, one for the app. Keep both running.

### Terminal 1: the backend

```powershell
cd apps/api
uv run uvicorn bekhi_api.main:app --host 0.0.0.0 --port 8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`.

- `--host 0.0.0.0` lets a phone on the same Wi-Fi reach it. With `127.0.0.1` only this PC can.
- Add `--reload` to restart automatically when you save a Python file.
- The backend reads `.env` only when it starts, so restart it after changing keys.

### Terminal 2: the app

Pick one way to open it.

#### A. In the browser (quickest)

```powershell
cd apps/mobile
npx expo start --web
```

Opens `http://localhost:8081`. Voice works in the browser too. On Windows, reminders, alarms and
notes become Windows notifications and a text file, handled by the backend on this PC.

#### B. On your phone with Expo Go

1. Put the phone and the PC on the **same Wi-Fi**.
2. Start the dev server:

   ```powershell
   cd apps/mobile
   npx expo start --go
   ```

3. **iPhone:** scan the QR code with the Camera app. On a physical iPhone, Expo Go opens a dev
   server only when Expo CLI and Expo Go are signed in to the same Expo account: run
   `npx expo login` once.
   **Android:** open Expo Go and scan the QR code, or tap *Enter URL manually* and type
   `exp://<your PC's IP>:8081`.

If the phone can't connect (public or office Wi-Fi often blocks devices from seeing each other):

```powershell
npx expo start --go --tunnel
```

#### C. As an installed Android app (APK)

Built in the cloud with EAS. See [apps/mobile/README.md](apps/mobile/README.md#install-on-android-as-an-app-apk).

#### D. The cloud web app on your PC, with the PC agent

https://bekhi.pages.dev talks to the cloud API (https://bekhi-api.onrender.com), so it needs nothing
running on your PC to chat. To let it do things **on this PC** (reminders and alarms as Windows toasts,
notes, opening apps and folders, the volume, locking the screen), start BEKHI's PC agent and keep its
window open:

```powershell
cd apps/api
.\bekhi-agent.cmd        # or: uv run python -m bekhi_api.agent
```

The agent is this same API on `127.0.0.1:8000`, answering only this PC's own requests; it needs no API
keys. Alarms and timers you set on your phone (with the same sync code) are pulled from the cloud and
ring on the PC too. The first time, the browser may ask whether bekhi.pages.dev may use apps on this
device: allow it. Without the agent, BEKHI says the PC action is not possible.

### How the app finds the backend

You don't configure an address. The app tries, in order:

1. `EXPO_PUBLIC_API_URL` from `apps/mobile/.env`, if you set one.
2. The same host that serves the app: `localhost:8000` in the browser, your PC's address in Expo Go.
3. The address that worked last time.
4. Every address on the phone's Wi-Fi, looking for `/api/v1/health` on port 8000.

If none of them answers, the app runs in **offline preview** mode with canned replies. That's how
you can tell the backend isn't reachable.

---

## Checking that it works

1. Open [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) on the PC. You
   should get `"status": "ok"` and a list of which providers have keys.
2. From the phone, open `http://<your PC's IP>:8000/api/v1/health` in the phone's browser. If this
   fails, the app can't reach the backend either; see [Troubleshooting](#troubleshooting).
3. In the app, tap the orb 🎙️ and say *"Сайн уу"*. You should see your words, then hear a reply.

Find your PC's IP with `ipconfig` (Windows; look for **IPv4 Address** under your Wi-Fi adapter) or
`ipconfig getifaddr en0` (macOS).

### Talking to BEKHI

Tap 🎙️ and speak. Recording stops about 1.3 s after you stop talking (or tap ■). BEKHI answers in
text and reads it aloud. After a question it listens again for your answer, so you can keep talking
hands-free. It stops listening after 7 s of silence, when you type, or when you tap 🎙️ while it is
speaking (that also cuts the reply short).

Some things to say:

| Say | What happens |
|---|---|
| "Өглөөний мэнд" / "Өнөөдөр юу байна?" | The day at a glance: weather, to-dos due today or overdue, what is scheduled today |
| "Өглөө бүр 7 цагт өдрийн тоймоо хэлж байгаарай" | A notification every morning at 7; tap it and BEKHI tells you the day |
| "YouTube-ээс Монгол дуу хай" / "Spotify асаа" / "Хаан банкны аппаа нээ" | Opens the app (and its search). Android's BEKHI app opens any installed app by name |
| "Маргааш 8 цагт сэрээгээрэй" / "10 минутын таймер" | An alarm or timer on every linked device |
| "Тайлан бичихийг жагсаалтад нэм" / "Хийх зүйлс юу байна?" | Your to-do list, shared by the devices linked with your sync code |
| "Ээж рүү залга" | Finds the contact (any script) and asks before calling |

---

## Everyday workflow

**Starting:** the two commands from [Running the project](#running-the-project).

**Restarting:** press `Ctrl+C` in the terminal and run the same command again.

| You changed… | Do this |
|---|---|
| `apps/api/.env` | Restart the backend |
| Python code | Restart the backend (or run it with `--reload`) |
| App code (`.tsx`, `.ts`) | Nothing; the app reloads by itself. Press `r` in the Expo terminal to force it |
| `app.json`, `apps/mobile/.env`, or after a strange error | Restart Expo with a clean cache: `npx expo start -c` |
| `packages/contracts/src` | `npm run contracts:export` (regenerates `generated/*.json`, which the backend reads) |
| After `git pull` | `npm install` at the root and `uv sync` in `apps/api` (packages may have changed) |

**Stopping:** `Ctrl+C` in both terminals.

---

## Tests and checks

Run these before opening a pull request. CI runs the first two on every push.

```powershell
npm run typecheck          # TypeScript: app + contracts
npm test                   # contract tests (vitest)

cd apps/mobile
npx expo lint              # app lint

cd ../api
uv run pytest              # backend tests, offline with a fake LLM
uv run pytest -m live -v   # the intent fixtures through real Gemini (needs GEMINI_API_KEY)
```

---

## Troubleshooting

**`uv : The term 'uv' is not recognized`**
`uv` is installed but your terminal was opened before. Open a new terminal, or for this one only:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
```

**`Could not import module "duud_api.main"`**
The project was renamed from Duud to BEKHI. The module is now `bekhi_api`:
`uv run uvicorn bekhi_api.main:app --host 0.0.0.0 --port 8000`. Run `npm install` at the root too,
so the app links `@bekhi/contracts`.

**`error while attempting to bind on address ('0.0.0.0', 8000)`: port 8000 is busy**
A backend is already running, probably in another terminal. Stop it there, or find it with
`netstat -ano | findstr :8000` and end it with `taskkill /PID <pid> /F`.

**The app shows canned replies (offline preview)**
The app can't reach the backend:
- Is the backend running with `--host 0.0.0.0`?
- Are the phone and PC on the same Wi-Fi? Can the phone's browser open `http://<PC IP>:8000/api/v1/health`?
- Windows Firewall: allow Python on **private** networks when Windows asks, or set your Wi-Fi
  connection to *Private*.

**The phone can't open the app in Expo Go**
Use `npx expo start --go --tunnel`. On an iPhone, sign in to the same Expo account in Expo Go and
with `npx expo login`.

**No voice reply, or a different voice than expected**
ElevenLabs is out of credits, the key is wrong, or the voice needs a paid plan. Set
`ELEVENLABS_VOICE_ID` to a premade voice (Adam: `pNInz6obpgDQGcFmaJgB`) and/or
`TTS_FALLBACK_PROVIDER=gemini`. A provider that fails for an account reason is skipped for 10 minutes.

**Speech isn't recognized**
Duudlaga may be out of credits. Set `STT_FALLBACK_PROVIDER=gemini`. The health endpoint shows which
keys the backend loaded.

**Gemini answers 429 / 503**
Rate limit or overload. The backend tries `GEMINI_FALLBACK_MODELS` in order; on the free tier, wait
a minute or use a paid key.

**Web search fails**
Set `TAVILY_API_KEY`. `WEB_SEARCH_PROVIDER=gemini` needs billing on the Gemini key.

---

## Further reading

- [docs/architecture.md](docs/architecture.md): the turn lifecycle and design decisions
- [docs/ios-capabilities.md](docs/ios-capabilities.md): what iOS allows and what BEKHI must not claim
- [docs/roadmap.md](docs/roadmap.md): phases, reordered toward Milestone 1
- [docs/speech-models.md](docs/speech-models.md): BuzzASR, Gemini, OronTTS — hardware, deployment, licensing
- [apps/api/README.md](apps/api/README.md): backend modules, endpoints, speech providers
- [apps/mobile/README.md](apps/mobile/README.md): app structure, Expo Go vs development build, APK
