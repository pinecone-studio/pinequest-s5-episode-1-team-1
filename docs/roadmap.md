# Roadmap

**Milestone 1 gates everything after Phase 12.** On a real iPhone:

> "Маргааш 9 цагт ажилтайг минь сануулаарай."
> voice → Mongolian STT → LLM → `create_reminder` → React Native → Swift → EventKit
> → Reminder visible in the Reminders app → Mongolian TTS reply

The fastest path to Milestone 1 reorders the original phases. Only what the reminder flow needs
gets built first:

| Order | Phase | Scope for Milestone 1 | Status |
|-------|-------|-----------------------|--------|
| 1 | P1 Monorepo + contracts | layout, wire contract, tool manifest, fixtures, docs, CI | ✅ |
| 2 | P2 Expo app | Expo Router, Zustand store, main screen states, IOSActionService, preview client (runs in Expo Go) | ✅ |
| 3 | P3 FastAPI | app skeleton, `/health`, config, provider interfaces, Pydantic ⇄ contracts test | ⬜ |
| 4 | P4 Audio recording | `expo-audio` 16 kHz mono WAV recording (`AUDIO_UPLOAD`), mic permission, upload | ⬜ |
| 5 | P5 STT | `apps/speech` with BuzzASR (CPU locally, GPU host); measure CER on real recordings of `intent-cases.json` | ⬜ |
| 6 | P6 LLM planner | Gemini function calling, system prompt, date resolution, run `intent-cases.json` | ⬜ |
| 7 | P7 Tool registry | registry loads `tools.manifest.json`; `create_reminder` + backend tools | ⬜ |
| 8 | P9 Swift action service | Expo module `DuudIOSActions`, `IOSActionService` TS interface | ⬜ |
| 9 | P12 Reminders | EventKit reminder end to end | ⬜ |
| 10 | P16 TTS | OronTTS in `apps/speech` (female/male, text normalizer), `/assistant/tts` | ⬜ |
| 11 | P21 + P22 | EAS dev build, **Milestone 1 on a real iPhone** | ⬜ |
| — | P8 Supabase | auth + persistence. Milestone 1 can run with an in-memory store behind the same repository interface | ⬜ |
| — | P10, P11, P13 | Contacts/call, Calendar, Maps | ⬜ |
| — | P14, P15 | App Intents + Shortcuts | ⬜ |
| — | P17–P20 | memory, confirmation UX, errors and permissions, test hardening | ⬜ |
| — | P23 | production deployment (Railway/Render, Sentry) | ⬜ |
