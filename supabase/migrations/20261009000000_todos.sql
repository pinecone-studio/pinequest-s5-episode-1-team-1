-- Each account's to-do list (apps/api todos.py). account_hash is the SHA-256 of the device-linking
-- sync code, as in sync_alarms: every device linked with one code shares the list.
-- Only the FastAPI backend (service role) reads and writes it: RLS is on and there are no policies.

create table public.todos (
  id           uuid primary key,
  account_hash text not null check (char_length(account_hash) = 64),
  title        text not null check (char_length(title) between 1 and 200),
  -- ISO-8601 as the assistant planned it, with the user's UTC offset ("2026-10-09T09:00:00+08:00"),
  -- kept as written so replies say the user's local time.
  due_at       text,
  done         boolean not null default false,
  -- The asking device's clock, same format.
  created_at   text not null
);

create index todos_account_created on public.todos (account_hash, created_at);

alter table public.todos enable row level security;
