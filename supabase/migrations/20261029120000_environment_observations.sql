-- Consolidated, versioned observations from existing Jarvis desktop and Android clients.
-- The API uses the server-only service role; client roles never access this table directly.
create table if not exists public.jarvis_environment_observations (
    id uuid primary key default gen_random_uuid(),
    user_id text not null check (length(user_id) between 1 and 320),
    device_id text not null check (length(device_id) between 1 and 128),
    source_device_type text not null check (source_device_type in ('desktop', 'mobile')),
    observation_type text not null check (observation_type in ('network_snapshot', 'presence')),
    schema_version integer not null default 1 check (schema_version = 1),
    request_id uuid not null,
    observed_at timestamptz not null,
    received_at timestamptz not null default now(),
    expires_at timestamptz not null,
    payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
    constraint jarvis_environment_observations_idempotency unique (user_id, request_id),
    constraint jarvis_environment_observations_expiry check (expires_at > received_at)
);

create index if not exists jarvis_environment_observations_latest_idx
    on public.jarvis_environment_observations (user_id, received_at desc);
create index if not exists jarvis_environment_observations_device_latest_idx
    on public.jarvis_environment_observations
       (user_id, device_id, source_device_type, observation_type, received_at desc);

alter table public.jarvis_environment_observations enable row level security;
revoke all on table public.jarvis_environment_observations from public, anon, authenticated, service_role;
grant select, insert on table public.jarvis_environment_observations to service_role;
