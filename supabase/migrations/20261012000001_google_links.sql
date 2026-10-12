-- Each account's Google link (apps/api google_link.py), for the cloud API: the Google account's
-- email and name, the permissions given (scopes), and the refresh token, encrypted with the API's
-- GOOGLE_TOKEN_KEY. BEKHI on the user's own computer keeps its link in a file there instead.
-- account_hash is the SHA-256 of the sync code, as in todos. Only the FastAPI backend (service role)
-- reads and writes it: RLS is on and there are no policies.

create table public.google_links (
  account_hash  text primary key check (char_length(account_hash) = 64),
  email         text not null default '',
  name          text not null default '',
  scopes        text not null default '',
  refresh_token text not null
);

alter table public.google_links enable row level security;
