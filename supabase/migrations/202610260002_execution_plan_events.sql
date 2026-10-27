-- Durable append-only journal for declarative execution plans.
-- Apply after the existing multi-agent migrations. The service-role client is
-- the only writer; client-facing roles receive no table privileges.
create table if not exists public.execution_plan_events (
    event_id uuid primary key default gen_random_uuid(),
    execution_id text not null check (length(execution_id) between 1 and 128),
    event_type text not null check (length(event_type) between 1 and 80),
    step_id text null check (step_id is null or length(step_id) <= 128),
    tool_name text null check (tool_name is null or length(tool_name) <= 200),
    status text null check (status is null or length(status) <= 40),
    error_code text null check (error_code is null or length(error_code) <= 100),
    duration_ms bigint null check (duration_ms is null or duration_ms >= 0),
    metadata jsonb not null default '{}'::jsonb
        check (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz not null default now()
);

create index if not exists execution_plan_events_execution_created_idx
    on public.execution_plan_events (execution_id, created_at, event_id);

alter table public.execution_plan_events enable row level security;

revoke all on table public.execution_plan_events from anon, authenticated;
grant select, insert on table public.execution_plan_events to service_role;

comment on table public.execution_plan_events is
    'Append-only operational journal. Never store raw arguments, secrets, or tool results.';
