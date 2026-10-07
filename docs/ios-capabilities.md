# What iOS actually allows Duud to do

Minimum target: **iOS 17**. Some features need newer versions, as marked.
Source of truth for runtime behaviour: `packages/contracts/src/tools.ts` (`TOOL_MANIFEST`).
Re-verify every row against the current iOS SDK when its phase is implemented.

| Tool | Mechanism | Needs user interaction? | Can report real success? | Permission (Info.plist key) |
|------|-----------|------------------------|--------------------------|-----------------------------|
| create_reminder | EventKit `EKReminder` + `EKAlarm` | No | **Yes** | `NSRemindersFullAccessUsageDescription` |
| create_calendar_event | EventKit `EKEvent`, write-only access (iOS 17+) | No | **Yes** | `NSCalendarsWriteOnlyAccessUsageDescription` |
| create_alarm | **AlarmKit** (iOS 26+) | No (after one-time authorization) | **Yes** | `NSAlarmKitUsageDescription` |
| create_alarm (< iOS 26) | User-installed Shortcut using Clock › "Create Alarm", run via `shortcuts://run-shortcut` | Yes, the app switches to Shortcuts | No → `handed_off` | — |
| call_contact | Contacts framework lookup → `tel:` URL | **Yes**, iOS shows its own call prompt | No → `handed_off` | `NSContactsUsageDescription` |
| send_message | `MFMessageComposeViewController` | **Yes**, the user taps Send | Yes (sent / cancelled / failed) | `NSContactsUsageDescription` |
| open_maps | `https://maps.apple.com/?daddr=…&dirflg=d`; `comgooglemaps://` if installed | Opens Maps | No → `handed_off` | `LSApplicationQueriesSchemes: comgooglemaps` |
| create_note | Stored inside Duud; optional Shortcut to Apple Notes | No / Yes | Yes (in-app) / `handed_off` | — |
| reminders-as-notification | `UNUserNotificationCenter` local notification | No | Yes (scheduled) | notification authorization |
| get_weather / web_search / get_current_time | FastAPI | No | Yes | — |

## Things Duud must NOT claim to do

| Request | Reality | What Duud says / offers |
|---------|---------|-------------------------|
| "Wi-Fi асаа", "Bluetooth унтраа", airplane mode, brightness, volume | No public API. Apps can't toggle system settings. | Explains the limitation. Suggests Control Center, or a user-made Shortcut ("Set Wi-Fi" / "Set Bluetooth"). Can open Duud's own Settings page. |
| Add an alarm to the **Clock app's** list | No API. AlarmKit alarms belong to Duud: they ring like alarms and show on the Lock Screen/Dynamic Island, but they are not Clock entries. | Says "Duud-ийн сэрүүлэг" honestly. |
| Alarm on iOS < 26 | No API at all. | Offers the Shortcut flow, or an explicit "notification instead?" question. A notification never replaces an alarm silently: it doesn't ring through Silent mode. |
| Place a call / send SMS without the user tapping | Not allowed. | Always confirms in Duud first. iOS then shows its own UI. |
| CallKit for cellular calls | CallKit is for an app's own VoIP calls only. | Not used for `call_contact`. |
| Send via Messenger/Telegram/WhatsApp silently | No public API. Only URL schemes that open the app. | Later phase, `handed_off` only. |
| "Hey Siri" in Mongolian | **Siri doesn't support Mongolian.** App Shortcut phrases can only be in Siri-supported languages. | Duud's App Shortcuts get English phrases ("Ask Duud"). For Mongolian voice entry, the user opens Duud from the Action Button, a Lock Screen / Control Center control (iOS 18+ Controls), or Back Tap. |
| Always-on wake word ("Дуудаа…") | Third-party apps can't listen in the background for a hotword. | Not offered. |
| Read Apple Notes / write to Apple Notes directly | No API. | In-app notes, or a Shortcut. |
| Limited contacts (iOS 18+) | The user may share only some contacts with Duud. | When "Ээж" isn't found under limited access, Duud says so and offers the system contact picker to add access. |

## Expo specifics

- **Expo Go can't run Duud.** Custom Swift modules, AlarmKit, App Intents and MessageUI need a
  **development build** (`expo-dev-client`) built with `expo prebuild` / EAS Build.
- From Windows there's no local Xcode. Builds go through **EAS Build (cloud)**. Installing on a
  real iPhone needs a **paid Apple Developer Program** membership, for device registration and
  provisioning.
- App Intents must be compiled into the main app target. We'll use a config plugin and
  verify after prebuild that `Metadata.appintents` is present in the built `.app`.
- An app can declare up to 10 App Shortcuts (`AppShortcutsProvider`).
