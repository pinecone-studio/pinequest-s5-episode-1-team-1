# BEKHI

Mongolian voice-first personal assistant for iPhone.

The user speaks Mongolian, casual and mixed with English. BEKHI works out the intent and runs
the action with **officially supported iOS APIs**, then replies in natural Mongolian.
It never claims an action succeeded unless the iPhone confirmed it.

```
apps/mobile         Expo dev build · Expo Router · Zustand · Swift native module    (Phase 2+)
apps/api            FastAPI · Pydantic · uv · Gemini LLM · CPU-only                 (Phase 3+)
apps/speech         GPU service · BuzzASR STT · OronTTS                             (Phase 5, 16)
packages/contracts  Wire contract (zod) · tool manifest · JSON Schema · fixtures
supabase            Migrations + RLS                                                (Phase 8)
docs                architecture · iOS capabilities · roadmap
```

- [docs/architecture.md](docs/architecture.md): the backend decides WHAT, the iPhone decides HOW, the turn lifecycle, decisions
- [docs/ios-capabilities.md](docs/ios-capabilities.md): what iOS allows and what BEKHI must not claim
- [docs/roadmap.md](docs/roadmap.md): phases, reordered toward Milestone 1
- [docs/speech-models.md](docs/speech-models.md): BuzzASR, Gemini, OronTTS — hardware, deployment, licensing

## Develop

```bash
npm install
npm run typecheck
npm test
npm run contracts:export   # after changing packages/contracts/src — regenerates generated/*.json
```

Requires Node ≥ 20.19. Python 3.12+ and `uv` are needed from Phase 3.
