-- Who each account is to BEKHI (apps/api profile.py): the user's name, their city and what the day's
-- briefing tells them, so the phone and the computer know the same person. account_hash is the
-- SHA-256 of the sync code, as in todos. Only the FastAPI backend (service role) reads and writes it:
-- RLS is on and there are no policies.

create table public.profiles (
  account_hash text primary key check (char_length(account_hash) = 64),
  -- {"name": ..., "city": ..., "briefing": ["weather", "todos", "schedule", "email", "news"]}
  data         jsonb not null default '{}'::jsonb,
  updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;
