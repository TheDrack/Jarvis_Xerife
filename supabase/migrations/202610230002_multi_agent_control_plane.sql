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
    task_id text primary key,
    parent_task_id text references public.jarvis_agent_tasks(task_id),
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
    task_id text not null references public.jarvis_agent_tasks(task_id),
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
    task_id text references public.jarvis_agent_tasks(task_id),
    attempt_id uuid references public.jarvis_agent_attempts(attempt_id),
    agent_id text,
    event_type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists jarvis_agent_events_task_idx
    on public.jarvis_agent_events (task_id, event_id);

-- The row lock serializes claims for the same agent and prevents the
-- concurrency counter from being oversubscribed by simultaneous requests.
create or replace function public.claim_jarvis_agent_task(
    p_task_id text,
    p_agent_id text,
    p_lease_seconds integer default 90
)
returns setof public.jarvis_agent_tasks
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_agent public.jarvis_agents%rowtype;
    v_task public.jarvis_agent_tasks%rowtype;
begin
    if p_lease_seconds < 10 or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    select * into v_agent
      from public.jarvis_agents
     where agent_id = p_agent_id
     for update;

    if not found
       or v_agent.status not in ('available', 'busy')
       or v_agent.active_tasks >= v_agent.concurrency_limit then
        return;
    end if;

    update public.jarvis_agent_tasks t
       set status = 'claimed',
           assigned_agent_id = p_agent_id,
           attempt_id = gen_random_uuid(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           fencing_token = t.fencing_token + 1,
           updated_at = now()
     where t.task_id = p_task_id
       and t.status = 'ready'
       and v_agent.available_tools @> to_jsonb(t.required_tools)
    returning t.* into v_task;

    if not found then
        return;
    end if;

    update public.jarvis_agents
       set active_tasks = active_tasks + 1,
           status = case when active_tasks + 1 >= concurrency_limit then 'busy' else status end,
           updated_at = now()
     where agent_id = p_agent_id;

    insert into public.jarvis_agent_attempts (
        attempt_id, task_id, agent_id, assigned_role, status, estimated_cost
    ) values (
        v_task.attempt_id, v_task.task_id, p_agent_id,
        initcap(replace(v_task.task_type, '_', ' ')), 'claimed',
        v_agent.estimated_cost + v_agent.coordination_cost
    );

    insert into public.jarvis_agent_events (
        task_id, attempt_id, agent_id, event_type, payload
    ) values (
        v_task.task_id, v_task.attempt_id, p_agent_id, 'task.claimed',
        jsonb_build_object('fencing_token', v_task.fencing_token,
                           'lease_expires_at', v_task.lease_expires_at)
    );

    return next v_task;
end;
$$;

-- Completion is tied to the current task owner and attempt; stale workers
-- cannot complete a task after a new attempt has been assigned.
create or replace function public.finish_jarvis_agent_task(
    p_task_id uuid,
    p_agent_id text,
    p_attempt_id uuid,
    p_status text,
    p_result jsonb default '{}'::jsonb
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_finished integer;
begin
    if p_status not in ('completed', 'failed', 'blocked', 'cancelled',
                        'recovery_pending', 'approval_required') then
        raise exception 'unsupported terminal/intermediate status';
    end if;

    update public.jarvis_agent_tasks
       set status = p_status,
           result = p_result,
           lease_expires_at = null,
           updated_at = now()
     where task_id = p_task_id
       and assigned_agent_id = p_agent_id
       and attempt_id = p_attempt_id
       and status in ('claimed', 'in_progress', 'verifying');

    get diagnostics v_finished = row_count;
    if v_finished = 0 then
        return false;
    end if;

    update public.jarvis_agents
       set active_tasks = greatest(active_tasks - 1, 0),
           status = case
               when status in ('offline', 'degraded') then status
               when greatest(active_tasks - 1, 0) < concurrency_limit then 'available'
               else 'busy'
           end,
           updated_at = now()
     where agent_id = p_agent_id;

    return true;
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
revoke all on function public.claim_jarvis_agent_task(text, text, integer) from public, anon, authenticated;
revoke all on function public.finish_jarvis_agent_task(text, text, uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_task(uuid, text, integer) to service_role;
grant execute on function public.finish_jarvis_agent_task(uuid, text, uuid, text, jsonb) to service_role;
grant select, insert, update on public.jarvis_agents to service_role;
grant select, insert, update on public.jarvis_agent_tasks to service_role;
grant select, insert, update on public.jarvis_agent_attempts to service_role;
grant select, insert on public.jarvis_agent_events to service_role;
grant usage, select on sequence public.jarvis_agent_events_event_id_seq to service_role;
