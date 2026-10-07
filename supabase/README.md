# supabase

**Phase 8.** SQL migrations with Row Level Security for:
`profiles` (linked to `auth.users`), `conversations`, `messages`, `tool_calls`, `user_preferences`, `device_capabilities`.

Data policy: no raw audio, no contact phone numbers, no message bodies beyond what the conversation
text already contains. `tool_calls` stores tool name, normalized arguments and status only.
