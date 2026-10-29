-- Native mobile event delivery and provider-neutral device registry for Jarvis Mobile.
-- A later forward migration expands the event type constraint to include notifications.

grant usage on schema public to service_role;

create table if not exists public.jarvis_mobile_devices (
    user_id text not null,
    device_id text not null check (length(device_id) between 1 and 128),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    revoked_at timestamptz,
    primary key (user_id, device_id)
);

create index if not exists jarvis_mobile_devices_active_idx
    on public.jarvis_mobile_devices (user_id, device_id)
    where revoked_at is null;

create table if not exists public.jarvis_mobile_push_events (
    event_id uuid primary key,
    user_id text not null,
    device_id text not null check (length(device_id) between 1 and 128),
    event_type text not null check (event_type in ('speak')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    delivered_at timestamptz,
    acknowledged_at timestamptz,
    attempts integer not null default 0 check (attempts >= 0),
    check (expires_at > created_at),
    check (expires_at <= created_at + interval '15 minutes')
);

create index if not exists jarvis_mobile_push_events_pending_idx
    on public.jarvis_mobile_push_events (user_id, device_id, expires_at)
    where acknowledged_at is null;

alter table public.jarvis_mobile_devices enable row level security;
alter table public.jarvis_mobile_push_events enable row level security;

revoke all on table public.jarvis_mobile_devices from public, anon, authenticated;
revoke all on table public.jarvis_mobile_push_events from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_mobile_devices to service_role;
grant select, insert, update, delete on table public.jarvis_mobile_push_events to service_role;
