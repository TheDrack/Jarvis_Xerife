-- Replace the legacy provider-token registry with a provider-neutral mobile registry.
-- Removes the legacy provider-token table on installations that already applied the earlier schema.

drop table if exists public.jarvis_mobile_push_devices;

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

alter table public.jarvis_mobile_devices enable row level security;
revoke all on table public.jarvis_mobile_devices from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_mobile_devices to service_role;

alter table public.jarvis_mobile_push_events
    drop constraint if exists jarvis_mobile_push_events_event_type_check;
alter table public.jarvis_mobile_push_events
    add constraint jarvis_mobile_push_events_event_type_check
    check (event_type in ('speak', 'notification'));
