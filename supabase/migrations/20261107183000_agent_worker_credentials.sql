-- Per-agent credentials for authenticated HTTP task workers.
-- Raw bearer tokens are returned once by the provisioning tool; only SHA-256
-- hashes are stored. Browser/client roles receive no access to this table.

create table if not exists public.jarvis_agent_credentials (
    credential_id uuid primary key default gen_random_uuid(),
    agent_id text not null references public.jarvis_agents(agent_id) on delete cascade,
    principal_id text not null check (length(principal_id) between 1 and 200),
    token_hash text not null unique
        check (token_hash ~ '^[0-9a-f]{64}$'),
    available_tools jsonb not null default '[]'::jsonb
        check (jsonb_typeof(available_tools) = 'array'),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    last_used_at timestamptz,
    revoked_at timestamptz,
    check (
        expires_at > created_at
        and expires_at <= created_at + interval '90 days'
    )
);

create index if not exists jarvis_agent_credentials_active_agent_idx
    on public.jarvis_agent_credentials (agent_id, expires_at)
    where revoked_at is null;

alter table public.jarvis_agent_credentials enable row level security;
revoke all on table public.jarvis_agent_credentials from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_agent_credentials to service_role;

comment on table public.jarvis_agent_credentials is
    'Per-agent opaque bearer credentials; token_hash only, service_role access only.';
comment on column public.jarvis_agent_credentials.available_tools is
    'Server-provisioned capability grant; never copied from heartbeat request payloads.';
