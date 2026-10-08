# supabase

**Phase 8.** SQL migrations with Row Level Security for:
`profiles` (linked to `auth.users`), `conversations`, `messages`, `tool_calls`, `user_preferences`, `device_capabilities`.

Data policy: no raw audio, no contact phone numbers, no message bodies beyond what the conversation
text already contains. `tool_calls` stores tool name, normalized arguments and status only.

## Alarm/timer sync (in use)

`migrations/20261008000000_sync_alarms.sql`: `sync_devices` and `sync_alarms`, keyed by the SHA-256 of a
device-linking sync code (the code itself is never stored). RLS is on with no policies: only the FastAPI
backend, using `SUPABASE_SERVICE_ROLE_KEY`, reads and writes them. Set `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` in `apps/api/.env`. Without them the API keeps synced alarms in memory, which
works only while every linked device talks to the same API.
