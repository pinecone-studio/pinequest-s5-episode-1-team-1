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

## To-do lists (in use)

`migrations/20261009000000_todos.sql`: `todos`, one list per account (the same sync-code hash), read and
written only by the backend with the service role key. Without Supabase the API keeps a JSON file per
account next to `TODO_FILE`; a request without a sync code (an app from before accounts) uses the one list
in `TODO_FILE` itself.

## Remembered facts (in use)

`migrations/20261010000000_memories.sql`: `memories`, the short facts each account asked BEKHI to remember
("Хэрэглэгчийн эхнэрийг Сараа гэдэг"), at most 50, read and written only by the backend. Without Supabase
they are a JSON file per account next to `MEMORY_FILE`.
