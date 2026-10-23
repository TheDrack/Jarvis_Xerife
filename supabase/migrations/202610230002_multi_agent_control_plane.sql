-- Jarvis multi-agent control plane.
-- Apply only after reviewing against the target Supabase project.
-- This migration does not grant direct table access to browser clients.

create table if not exists public.jarvis_agents (
    agent_id text primary key,
    runtime_version text not null,
    environment text not null default 'unknown',
    available_tools jsonb not null default '[]'::jsonb
        check (jsonb_typeof(available_tools) = 'array'),
    status text not null default 'offline'
        check (status in ('available', 'busy', 'offline', 'degraded')),
    active_tasks integer not null default 0 check (active_tasks >= 0),
    concurrency_limit integer not null default 1 check (concurrency_limit > 0),
    estimated_cost numeric(14, 6) not null default 0 check (estimated_cost >= 0),
    coordination_cost numeric(14, 6) not null default 0 check (coordination_cost >= 0),
    success_rates jsonb not null default '{}'::jsonb
        check (jsonb_typeof(success_rates) = 'object'),
    last_seen_at timestamptz,
    updated_at timestamptz not null default now()
);

create table if not exists public.jarvis_agent_tasks (
    task_id uuid primary key,
    parent_task_id uuid references public.jarvis_agent_tasks(task_id),
    objective text not null,
    task_type text not null default 'general',
    required_tools text[] not null default '{}',
    constraints jsonb not null default '[]'::jsonb,
    acceptance_criteria jsonb not null default '[]'::jsonb,
    expected_value numeric(14, 6) not null default 1 check (expected_value >= 0),
    max_cost numeric(14, 6) check (max_cost is null or max_cost >= 0),
    risk_level text not null default 'low'
        check (risk_level in ('low', 'medium', 'high', 'critical')),
    status text not null default 'ready'
        check (status in (
            'proposed', 'ready', 'claimed', 'in_progress', 'verifying',
            'completed', 'blocked', 'failed', 'cancelled',
            'recovery_pending', 'approval_required'
        )),
    leader_id text not null,
    assigned_agent_id text references public.jarvis_agents(agent_id),
    attempt_id uuid,
    lease_expires_at timestamptz,
    fencing_token bigint not null default 0,
    result jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists jarvis_agent_tasks_ready_idx
    on public.jarvis_agent_tasks (status, created_at)
    where status in ('ready', 'blocked');

create index if not exists jarvis_agent_tasks_owner_idx
    on public.jarvis_agent_tasks (assigned_agent_id, status);

create table if not exists public.jarvis_agent_attempts (
    attempt_id uuid primary key,
    task_id uuid not null references public.jarvis_agent_tasks(task_id),
    agent_id text not null references public.jarvis_agents(agent_id),
    assigned_role text not null,
    status text not null default 'claimed'
        check (status in (
            'claimed', 'in_progress', 'verifying', 'completed', 'failed',
            'cancelled', 'recovery_pending', 'approval_required'
        )),
    estimated_cost numeric(14, 6) not null default 0,
    actual_cost numeric(14, 6),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_summary text,
    evidence jsonb not null default '[]'::jsonb
);

create table if not exists public.jarvis_agent_events (
    event_id bigint generated always as identity primary key,
    task_id uuid references public.jarvis_agent_tasks(task_id),
    attempt_id uuid references public.jarvis_agent_attempts(attempt_id),
    agent_id text,
    event_type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists jarvis_agent_events_task_idx
    on public.jarvis_agent_events (task_id, event_id);

-- Claim is atomic. The fencing token increments every time a lease is claimed
-- or reclaimed, allowing receivers to reject stale commands from old owners.
create or replace function public.claim_jarvis_agent_task(
    p_task_id uuid,
    p_agent_id text,
    p_lease_seconds integer default 90
)
returns setof public.jarvis_agent_tasks
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if p_lease_seconds < 10 or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    return query
    update public.jarvis_agent_tasks t
       set status = 'claimed',
           assigned_agent_id = p_agent_id,
           attempt_id = gen_random_uuid(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           fencing_token = t.fencing_token + 1,
           updated_at = now()
      from public.jarvis_agents a
     where t.task_id = p_task_id
       and a.agent_id = p_agent_id
       and a.status = 'available'
       and a.active_tasks < a.concurrency_limit
       and a.available_tools @> to_jsonb(t.required_tools)
       and (
            t.status = 'ready'
            or (t.status = 'claimed' and t.lease_expires_at < now())
       )
    returning t.*;
end;
$$;

-- Append-only event log.
create or replace function public.jarvis_reject_agent_event_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'jarvis_agent_events is append-only';
end;
$$;

drop trigger if exists jarvis_agent_events_no_update on public.jarvis_agent_events;
create trigger jarvis_agent_events_no_update
    before update or delete on public.jarvis_agent_events
    for each row execute function public.jarvis_reject_agent_event_mutation();

alter table public.jarvis_agents enable row level security;
alter table public.jarvis_agent_tasks enable row level security;
alter table public.jarvis_agent_attempts enable row level security;
alter table public.jarvis_agent_events enable row level security;

revoke all on public.jarvis_agents from anon, authenticated;
revoke all on public.jarvis_agent_tasks from anon, authenticated;
revoke all on public.jarvis_agent_attempts from anon, authenticated;
revoke all on public.jarvis_agent_events from anon, authenticated;
revoke all on function public.claim_jarvis_agent_task(uuid, text, integer) from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_task(uuid, text, integer) to service_role;
grant select, insert, update on public.jarvis_agents to service_role;
grant select, insert, update on public.jarvis_agent_tasks to service_role;
grant select, insert, update on public.jarvis_agent_attempts to service_role;
grant select, insert on public.jarvis_agent_events to service_role;
grant usage, select on sequence public.jarvis_agent_events_event_id_seq to service_role;
