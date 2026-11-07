-- Shared execution recovery history. Metadata only; snapshot bytes stay in local/object storage.
-- Apply only after PR review and confirmation of the target Supabase project.

create table if not exists public.jarvis_recovery_runs (
    run_id uuid primary key default gen_random_uuid(),
    correlation_id text,
    agent_id text not null,
    environment_id text not null,
    source text not null,
    status text not null default 'running'
      check (status in ('running','succeeded','failed','degraded','recovery_required','recovered')),
    risk_level text not null default 'low'
      check (risk_level in ('low','reversible','high','destructive')),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    metadata jsonb not null default '{}'::jsonb
);
create index if not exists ix_jarvis_recovery_runs_started on public.jarvis_recovery_runs(started_at desc);
create index if not exists ix_jarvis_recovery_runs_correlation on public.jarvis_recovery_runs(correlation_id);

create table if not exists public.jarvis_recovery_events (
    event_id uuid primary key,
    run_id uuid not null references public.jarvis_recovery_runs(run_id) on delete restrict,
    operation_id text,
    event_type text not null,
    actor_id text not null,
    payload jsonb not null default '{}'::jsonb,
    previous_event_hash text,
    event_hash text,
    created_at timestamptz not null default now()
);
create index if not exists ix_jarvis_recovery_events_run on public.jarvis_recovery_events(run_id,created_at);
create index if not exists ix_jarvis_recovery_events_operation on public.jarvis_recovery_events(operation_id);

create table if not exists public.jarvis_recovery_checkpoints (
    checkpoint_id uuid primary key,
    run_id uuid not null references public.jarvis_recovery_runs(run_id) on delete restrict,
    environment_id text not null,
    resource_type text not null,
    resource_ref text not null,
    content_hash text,
    storage_ref text,
    validation_status text not null default 'pending'
      check (validation_status in ('pending','valid','invalid','unavailable')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists ix_jarvis_recovery_checkpoints_run on public.jarvis_recovery_checkpoints(run_id,created_at);

create table if not exists public.jarvis_recovery_actions (
    action_id uuid primary key,
    run_id uuid not null references public.jarvis_recovery_runs(run_id) on delete restrict,
    operation_id text,
    strategy text not null,
    status text not null default 'planned'
      check (status in ('planned','awaiting_approval','running','succeeded','failed','blocked','verified')),
    approval_status text not null default 'not_required'
      check (approval_status in ('not_required','pending','approved','rejected')),
    idempotency_key text not null unique,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    verification_result jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists ix_jarvis_recovery_actions_run on public.jarvis_recovery_actions(run_id,created_at);

alter table public.jarvis_recovery_runs enable row level security;
alter table public.jarvis_recovery_events enable row level security;
alter table public.jarvis_recovery_checkpoints enable row level security;
alter table public.jarvis_recovery_actions enable row level security;
revoke all on public.jarvis_recovery_runs from anon, authenticated;
revoke all on public.jarvis_recovery_events from anon, authenticated;
revoke all on public.jarvis_recovery_checkpoints from anon, authenticated;
revoke all on public.jarvis_recovery_actions from anon, authenticated;
grant select,insert,update on public.jarvis_recovery_runs to service_role;
grant select,insert on public.jarvis_recovery_events to service_role;
grant select,insert,update on public.jarvis_recovery_checkpoints to service_role;
grant select,insert,update on public.jarvis_recovery_actions to service_role;

create or replace function public.jarvis_recovery_events_are_append_only()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception 'jarvis_recovery_events is append-only';
end;
$$;
drop trigger if exists jarvis_recovery_events_no_mutation on public.jarvis_recovery_events;
create trigger jarvis_recovery_events_no_mutation
before update or delete on public.jarvis_recovery_events
for each row execute function public.jarvis_recovery_events_are_append_only();
revoke all on function public.jarvis_recovery_events_are_append_only() from public,anon,authenticated;
