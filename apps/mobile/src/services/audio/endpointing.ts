/**
 * Decides from the microphone level when the user has finished speaking, so they do
 * not have to tap stop. Levels are dBFS (iOS `averagePower`, the same formula on web).
 *
 * The room's noise floor is learned while recording: it follows quiet readings down
 * at once and drifts up slowly, so a noisy room is not mistaken for speech.
 */
/** no_speech: the room was audible but nobody spoke. mic_silent: the input was pure silence
 *  the whole time, which a working microphone never gives (muted or wrong device). */
export type Verdict = "listening" | "done" | "no_speech" | "mic_silent";

const WARMUP_MS = 200; // the first readings after start are often -160
const DIGITAL_SILENCE_DB = -100; // input gated to zero (noise suppression, muted mic)
const MAX_INITIAL_FLOOR_DB = -45; // if the user is already talking at the first reading
const FLOOR_RISE = 0.01; // per reading, towards the current level
const SPEECH_ABOVE_FLOOR_DB = 10;
const QUIET_ABOVE_FLOOR_DB = 6; // between quiet and speech: keep the current state
const MIN_SPEECH_MS = 300; // ignore clicks and coughs
const END_SILENCE_MS = 1300;
const NO_SPEECH_MS = 7000;

export function createEndpointer() {
  let floor: number | null = null;
  let lastMs = 0;
  let speechMs = 0;
  let quietMs = 0;
  let heard = false;
  let signal = false; // any reading above digital silence

  function quiet(dt: number) {
    quietMs += dt;
    if (!heard) speechMs = 0;
  }

  return (level: number | undefined, elapsedMs: number): Verdict => {
    const dt = elapsedMs - lastMs;
    lastMs = elapsedMs;
    if (level === undefined) return "listening"; // no metering here: the user taps stop
    if (!heard && elapsedMs >= NO_SPEECH_MS) return signal ? "no_speech" : "mic_silent";
    if (elapsedMs < WARMUP_MS) return "listening";

    if (level < DIGITAL_SILENCE_DB) {
      quiet(dt); // silence, but not a room level worth learning
    } else {
      signal = true;
      floor = floor === null ? Math.min(level, MAX_INITIAL_FLOOR_DB) : level < floor ? level : floor + (level - floor) * FLOOR_RISE;
      if (level > floor + SPEECH_ABOVE_FLOOR_DB) {
        speechMs += dt;
        quietMs = 0;
        if (speechMs >= MIN_SPEECH_MS) heard = true;
      } else if (level < floor + QUIET_ABOVE_FLOOR_DB) {
        quiet(dt);
      }
    }
    return heard && quietMs >= END_SILENCE_MS ? "done" : "listening";
  };
}
