# apps/speech — Mongolian speech service (GPU)

**Phase 5 (STT) and Phase 16 (TTS).** A small internal FastAPI service that hosts both models.
Only `apps/api` calls it, with a bearer token. The phone never calls it.

| Endpoint | Model | In → Out |
|----------|-------|----------|
| `POST /v1/transcribe` | [BuzzASR/mongolian](https://huggingface.co/BuzzASR/mongolian), a Whisper-large-v3 fine-tune | 16 kHz mono WAV → `{ "text": "..." }` |
| `POST /v1/synthesize` | [OronTTS](https://github.com/btseee/oron-tts), an F5-TTS fine-tune | `{ "text", "voice": "female" \| "male" }` → 24 kHz WAV |
| `GET /health` | — | model load state |

It's separate from `apps/api` because the models need a GPU, and Railway/Render don't have GPUs.
See [docs/speech-models.md](../../docs/speech-models.md).
