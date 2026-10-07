# apps/api — Duud backend

Python 3.12+ · FastAPI · Pydantic · httpx · python-dotenv · google-genai, managed with `uv`.

The backend decides **what** should happen. It never performs iPhone actions and never says a
device action is done before the phone reports the real outcome.

```
src/duud_api/
  main.py            endpoints, Mongolian errors, CORS, rate limit, safe logging
  pipeline.py        text -> LLM function calls -> validated AssistantTurn; results -> final answer
  planner.py         system prompt + functions (tools from contracts + reply / ask_clarification / explain_limitation)
  contracts.py       validates tool args and outgoing turns against packages/contracts/generated
  compose.py         final Mongolian sentences from real outcomes (vowel harmony helpers)
  backend_tools.py   get_weather (Open-Meteo), get_current_time, web_search (Tavily)
  providers/         STT / TTS / LLM interfaces; Duudlaga, ElevenLabs and Gemini implementations, fallbacks
  store.py           in-memory conversations (Supabase in Phase 8)
```

## Run

```bash
uv sync
```

Put the key in `apps/api/.env` (git-ignored): `GEMINI_API_KEY=...`

```bash
uv run uvicorn duud_api.main:app --host 127.0.0.1 --port 8000
```

Use `--host 0.0.0.0` when an iPhone on the same network needs to reach it.

## Test

```bash
uv run pytest
```

Runs offline with a fake LLM. To run the intent fixtures through real Gemini (needs the key):

```bash
uv run pytest -m live -v
```

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `/api/v1/health` | provider status |
| POST | `/api/v1/assistant/chat` | `{text, context}` → AssistantTurn |
| POST | `/api/v1/assistant/voice` | multipart `audio` (16 kHz mono WAV) + `context` JSON → AssistantTurn |
| POST | `/api/v1/assistant/transcribe` | multipart `audio` → `{transcript}` |
| GET | `/api/v1/assistant/voices` | ElevenLabs voices the app can pick (`config.ELEVENLABS_VOICES`) and the default |
| POST | `/api/v1/assistant/tts` | `{text, voice?}` → MP3 (ElevenLabs) or WAV (Gemini fallback). A voice that needs a paid plan is read in the default voice, with `X-Duud-Voice-Fallback: paid_plan_required` |
| POST | `/api/v1/assistant/actions/results` | device outcomes → final Mongolian answer |
| POST | `/api/v1/desktop/actions` | `{tool, arguments}` → ActionResult, run on this Windows PC. Requests from localhost only; `DESKTOP_ACTIONS=false` turns it off |

Agent loop (`pipeline.py`): when Gemini calls a backend tool (`web_search`, `get_weather`,
`get_current_time`) it gets the result back and continues, up to 4 steps, then answers in its own
words. Device actions end the loop: their outcome only exists once the phone or PC reports it.
`web_search` uses Tavily (`TAVILY_API_KEY`, 1,000 free searches a month, results from Mongolia first).
`WEB_SEARCH_PROVIDER=gemini` uses Gemini's Google Search grounding instead, which a free-tier key does
not have (429).

Desktop actions (`desktop.py`): reminders, alarms and event reminders become Windows toast
notifications, kept in `%LOCALAPPDATA%\Duud\reminders.json` and fired by the running API (nothing is
registered with Windows, so they only fire while the API runs). Notes are appended to
`Documents\Duud тэмдэглэл.txt`. `open_app` launches an installed app found in the Start menu.
`set_timer`, `list_reminders` and `cancel_reminder` work on the same scheduled items (the iPhone does
the same with its local notifications). `computer_control` (`windows_controls.py`) sets the speaker
volume and mute through Core Audio, locks the screen, and opens Downloads/Documents/... folders.

## Speech providers

| | Main | Fallback (`STT_FALLBACK_PROVIDER` / `TTS_FALLBACK_PROVIDER`, empty = off) |
|---|---|---|
| STT | Duudlaga (`DUUDLAGA_API_KEY`) | Gemini: dedicated transcription model `gemini-3.5-transcribe-live`, then prompted `GEMINI_STT_MODEL` |
| TTS | ElevenLabs `eleven_v4` (`ELEVENLABS_API_KEY`, 51 characters), voice `ELEVENLABS_VOICE_ID`: "Ganbold" needs a paid plan, premade voices such as Adam work on the free plan | Gemini TTS (`GEMINI_TTS_MODELS`), WAV |

A main provider that fails for an account reason (no credits, wrong key) is skipped for 10 minutes,
so requests do not wait on it. `GET /api/v1/health` shows which providers have keys.

Gemini's prompted transcription is weak for Mongolian: on synthetic test clips it misheard about half
of the phrases, and the old prompt (which listed assistant topics) made it "hear" commands that were
never said. The dedicated transcription model got almost all of them right, so it goes first.

Gemini TTS is a stopgap: it takes 2–10 s per reply and the free tier allows only a few requests per
model per day. ElevenLabs answers in about a second.

Set `STT_PROVIDER=buzzasr` once `apps/speech` is deployed.
