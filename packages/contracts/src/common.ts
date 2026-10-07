import { z } from "zod";

/**
 * Absolute timestamp with an explicit UTC offset, e.g. "2026-10-07T09:00:00+08:00".
 *
 * The backend resolves every relative expression ("маргааш", "орой", "8д") into an
 * absolute timestamp before an action reaches the device. The mobile app never
 * parses natural-language dates.
 */
export const IsoDateTime = z.iso.datetime({ offset: true });

/** Calendar date, e.g. "2026-10-07". */
export const IsoDate = z.iso.date();

/** IANA timezone name. Mongolia (most of it) is "Asia/Ulaanbaatar", UTC+8. */
export const IanaTimezone = z.string().min(1).max(64);

export const DEFAULT_TIMEZONE = "Asia/Ulaanbaatar";

/** Opaque id for one action inside one assistant turn. */
export const ActionId = z.string().min(1).max(64);

export const Uuid = z.uuid();

/** Short user-facing Mongolian text (spoken + shown). */
export const SpokenText = z.string().max(1000);

/**
 * Upload format for POST /assistant/voice. Matches what BuzzASR (Whisper) expects,
 * so the server never transcodes. 30 s of 16-bit PCM is ~0.96 MB.
 */
export const AUDIO_UPLOAD = {
  mime_type: "audio/wav",
  sample_rate_hz: 16000,
  channels: 1,
  bit_depth: 16,
  max_seconds: 30,
} as const;

/** The two curated OronTTS voices. Arbitrary reference audio is never accepted. */
export const TtsVoice = z.enum(["female", "male"]);
export type TtsVoice = z.infer<typeof TtsVoice>;
