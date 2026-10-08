# Speech and language models

| Role | Choice | Runs where |
|------|--------|------------|
| STT | [BuzzASR/mongolian](https://huggingface.co/BuzzASR/mongolian) | `apps/speech` (GPU) |
| LLM | Gemini (tool/function calling) | Google API, called from `apps/api` |
| TTS | [OronTTS](https://github.com/btseee/oron-tts), weights [btsee/oron-tts](https://huggingface.co/btsee/oron-tts) | `apps/speech` (GPU) |

All three sit behind provider interfaces in `apps/api` (`providers/stt`, `providers/llm`, `providers/tts`).
OpenAI stays available as an alternative implementation.

## BuzzASR/mongolian (STT)

- Whisper-large-v3 fine-tune with a native Mongolian tokenizer. ~2B params, F16 (~4 GB of weights).
- Reported **5.21% CER / 13.34% WER** on FLEURS + Common Voice test sets (zero-shot Whisper-large-v3: 38.23% CER).
- Input is **16 kHz mono**. The iPhone records in exactly that format (`AUDIO_UPLOAD` in contracts), so the server never transcodes.
- License: MIT. Not gated.
- Trained on read speech (FLEURS, Common Voice). Casual speech, slang and Mongolian–English mixing are
  untested. Phase 5 must measure it on real recordings of the `intent-cases.json` utterances.
- Loading: `transformers` `pipeline("automatic-speech-recognition", model="BuzzASR/mongolian")`.

## OronTTS (TTS)

- F5-TTS v1 Base fine-tune (336M params) for Khalkha Cyrillic, with 24 kHz output (Vocos vocoder).
- Two voices, `female` and `male`. Each is a curated reference clip plus its transcript, shipped with the weights.
- Text must go through `oron_tts.text.MongolianNormalizer` first: numbers, times ("8:30") and abbreviations get spelled out.
- Inference: `F5TTS(model="F5TTS_v1_Base", ckpt_file, vocab_file, use_ema=False).infer(ref_file, ref_text, gen_text, nfe_step=32, cfg_strength=2.0)`.
- **Voice cloning risk:** F5-TTS reproduces whatever reference voice it's given. BEKHI only ever uses the
  two shipped voices. The API takes `voice: "female" | "male"` and never accepts uploaded reference audio.
- Young project (few stars, architecture was rebuilt recently). Pin the weights revision.

### ⚠ License — check before any commercial launch

- The OronTTS code is MIT. The weights card declares **CC-BY-4.0**, which needs **attribution**: the app's About
  screen credits OronTTS and the FLEURS dataset.
- The card says there's no non-commercial restriction. But the weights are a fine-tune of `F5TTS_v1_Base`,
  and upstream F5-TTS publishes those pretrained weights as CC-BY-NC-4.0 (because of its Emilia
  training data). The card doesn't address this. A derivative of NC weights may inherit the restriction.
- Fine for the prototype and personal testing. **Confirm with the author or a lawyer before charging money or launching publicly.**

## Hardware and deployment

- The dev machine has no NVIDIA GPU. Both models *run* on CPU (`DEVICE=cpu`), but slowly: expect seconds to tens of
  seconds per request. Good enough to check correctness, not latency.
- Railway and Render have no GPUs, so `apps/speech` deploys to a GPU host. Candidates: Modal, RunPod Serverless,
  HF Inference Endpoints. One GPU with ≥16 GB VRAM holds both models.
- Scale-to-zero means cold starts that load ~5 GB of weights. A voice assistant needs a warm instance, or a
  visible "loading" state. This is a cost decision for Phase 23.
- Latency budget per turn (target, to be measured): STT < 1.5 s, Gemini < 2 s, TTS < 1.5 s.
