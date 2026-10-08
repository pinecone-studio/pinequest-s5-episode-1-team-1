-- Alarms and timers shared by every device linked with one sync code (apps/api sync.py).
-- account_hash is the SHA-256 of the sync code; the code itself is never stored.
-- Only the FastAPI backend (service role) reads and writes these tables: RLS is on and
-- there are no policies, so the app's anon key gets nothing.

create table public.sync_devices (
  account_hash text not null check (char_length(account_hash) = 64),
  device_id    text not null check (char_length(device_id) between 8 and 64),
  platform     text not null check (platform in ('ios', 'android', 'web')),
  last_seen    timestamptz not null default now(),
  primary key (account_hash, device_id)
);

create table public.sync_alarms (
  id           uuid primary key,
  account_hash text not null check (char_length(account_hash) = 64),
  kind         text not null check (kind in ('alarm', 'timer')),
  title        text not null check (char_length(title) between 1 and 100),
  -- The exact moment it rings: a timer is stored as its end time, so every device rings together.
  fire_at      timestamptz not null,
  created_by   text not null,
  created_at   timestamptz not null default now(),
  cancelled_at timestamptz
);

create index sync_alarms_account_fire_at on public.sync_alarms (account_hash, fire_at);

alter table public.sync_devices enable row level security;
alter table public.sync_alarms enable row level security;

-- Past alarms are useless; run from pg_cron or by hand: delete ... where fire_at < now() - interval '1 day'.
