-- Link external identities to existing Jarvis accounts without replacing native credentials.
-- Private server-side table: all access is mediated by the service-role client.
create table if not exists public.jarvis_external_identities (
    id uuid primary key default gen_random_uuid(),
    provider text not null check (provider in ('google')),
    provider_subject text not null check (length(provider_subject) between 1 and 255),
    user_id text not null check (length(user_id) between 1 and 255),
    email text not null check (length(email) between 3 and 320),
    full_name text not null default '',
    created_at timestamptz not null default now(),
    unique (provider, provider_subject),
    unique (provider, user_id)
);

create index if not exists jarvis_external_identities_user_idx
    on public.jarvis_external_identities (user_id);

alter table public.jarvis_external_identities enable row level security;
revoke all on table public.jarvis_external_identities from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_external_identities to service_role;
