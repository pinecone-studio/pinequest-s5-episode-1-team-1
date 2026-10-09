-- What each account asked BEKHI to remember (apps/api memory.py): short facts about the user, given
-- to the planner with every request. account_hash is the SHA-256 of the sync code, as in todos.
-- Only the FastAPI backend (service role) reads and writes it: RLS is on and there are no policies.

create table public.memories (
  id           uuid primary key,
  account_hash text not null check (char_length(account_hash) = 64),
  text         text not null check (char_length(text) between 1 and 200),
  -- The asking device's clock, ISO-8601 with its UTC offset.
  created_at   text not null
);

create index memories_account_created on public.memories (account_hash, created_at);

alter table public.memories enable row level security;
