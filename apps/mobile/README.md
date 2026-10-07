# apps/mobile — Duud app (iPhone, Android, web)

Expo SDK 57 · Expo Router (`src/app`) · Zustand · TypeScript. Consumes `@duud/contracts` and
validates every assistant turn with it before acting.

```
src/app/                    screens (Expo Router)
src/store/assistant.ts      turn state machine: idle → processing → confirming → executing → success/unavailable/error
src/services/assistant/     AssistantClient interface · PreviewAssistantClient (until Phase 3) · context
src/services/ios-actions/   IOSActionService interface · Expo (iPhone) / ExpoAndroid / Desktop (web) implementations
src/services/audio/         recorder (16 kHz WAV; Android reads raw PCM and writes the WAV itself) · endpointing
src/services/speech/        plays the reply from POST /assistant/tts (expo-audio on iPhone, <audio> on web)
src/components/             SiriOrb (tap to talk) · EdgeGlow · Backdrop · MessageLine · TypeBar · ConfirmBar · VoicePicker
```

## Run on your iPhone with Expo Go (UI preview)

1. Install **Expo Go** from the App Store.
2. Put the phone on the same Wi-Fi as the PC.
3. Start the dev server:
   ```bash
   npx expo start --go
   ```
4. Scan the QR code with the iPhone Camera and open it in Expo Go.

If the phone can't connect (client isolation on the Wi-Fi, firewall), use `npx expo start --go --tunnel`.

## Run on an Android phone with Expo Go

1. Install **Expo Go** from Google Play.
2. Put the phone on the same Wi-Fi (or the same phone hotspot) as the PC.
3. With the dev server running, open Expo Go and either sign in to the same Expo account (the project
   shows up under Development servers) or tap *Enter URL manually*: `exp://<PC address>:8081`.

Android's recorder (MediaRecorder) cannot write WAV, so `useVoiceInput.android.ts` reads the microphone
as raw 16 kHz PCM (`useAudioStream`) and saves the same WAV the iPhone uploads; its RMS level drives the
same end-of-speech detection. The request context says `platform: "android"`, so the assistant talks
about an Android phone. Reminders, alarms and timers are local notifications; alarms and timers use a
channel that sounds on the alarm stream.

## Install on Android as an app (APK)

Built in the cloud with EAS (`eas.json`, profile `preview`: an installable APK, arm64 only). The repo has
no commits yet, so EAS runs without Git and uploads the monorepo minus `.easignore`:

```bash
cd apps/mobile
EAS_NO_VCS=1 EAS_PROJECT_ROOT=<repo root, absolute> npx eas-cli build -p android --profile preview
```

Copy the APK to the phone (USB file transfer into Download is enough) and open it there to install.
The installed app has no dev server to learn the PC's address from, so `connect.ts` tries the address
that answered last time and otherwise looks for the API on every address of the phone's Wi-Fi network
(`/api/v1/health`); it looks again when the app comes back to the foreground. The API is plain HTTP on
the LAN, hence `usesCleartextTraffic` (expo-build-properties). Exact-alarm permissions keep timers on time.

### What works in Expo Go and what doesn't

| | Expo Go (iPhone) | Expo Go (Android) | Development build (Phase 9+) | Browser on the PC that runs the API |
|---|---|---|---|---|
| Voice conversation (record → backend STT → reply → spoken reply) | ✅ | ✅ | ✅ | ✅ |
| Open maps (`open_maps`) | ✅ Apple Maps | ✅ Google Maps | ✅ | ✅ Google Maps tab |
| Call / message a contact | ✅ expo-contacts + `tel:` / message sheet | ✅ expo-contacts + dialer / SMS app | ✅ | ❌ |
| Reminder / alarm / event / timer | ⚠️ local notification at that time | ⚠️ local notification at that time | ✅ EventKit / AlarmKit | ⚠️ Windows toast while the API runs |
| Note | ❌ | ❌ | ✅ | ✅ appended to Documents\Duud тэмдэглэл.txt |
| Open another app, volume, lock screen | ❌ iOS does not allow it | ❌ needs a native build | | ✅ |

Expo Go never fakes success, and the reply says when something is only a notification. `expo-calendar`
is not in Expo Go (SDK 57), so real EventKit work needs a development build
(`eas build --profile development`, paid Apple Developer account).

On a physical iPhone, Expo Go opens a dev server only when Expo CLI and Expo Go are signed in to the
same Expo account (`npx expo login`). Since SDK 57 the global `fetch` is Expo's, which rejects React
Native's `{ uri, name, type }` FormData parts, so uploads pass a part with `bytes()` (audio-upload.ts).

## Talking to Duud

Tap 🎙️ and speak. Recording stops by itself about 1.3 s after you stop talking (or tap ■).
Duud answers in text and reads it aloud. After a voice question it listens again for your
answer, so you can keep talking hands-free. It stops listening after 7 s of silence, when you
type, or when you tap 🎙️ while it is speaking (that also cuts the reply short).

The backend has to be running (`apps/api`) and reachable from the phone: start it with
`--host 0.0.0.0` and keep the phone on the same Wi-Fi.
