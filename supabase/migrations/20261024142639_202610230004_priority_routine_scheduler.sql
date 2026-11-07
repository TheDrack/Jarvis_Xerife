-- Priority-aware dynamic task scheduling for the Jarvis multi-agent control plane.
-- Apply only after reviewing and confirming the target Supabase project.
-- Existing multi-agent tables are extended in place; no existing rows are deleted.

create table if not exists public.jarvis_routine_definitions (
    routine_id uuid primary key default gen_random_uuid(),
    routine_key text not null unique,
    name text not null,
    enabled boolean not null default true,
    priority integer not null default 50 check (priority between 0 and 1000),
    schedule jsonb not null default '{}'::jsonb,
    task_template jsonb not null default '{}'::jsonb,
    last_triggered_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.jarvis_agent_tasks
    add column if not exists priority integer not null default 50;
alter table public.jarvis_agent_tasks
    add column if not exists routine_id uuid references public.jarvis_routine_definitions(routine_id);
alter table public.jarvis_agent_tasks
    add column if not exists idempotency_key text;
alter table public.jarvis_agent_tasks
    add column if not exists attempts integer not null default 0;
alter table public.jarvis_agent_tasks
    add column if not exists max_attempts integer not null default 3;

alter table public.jarvis_agent_tasks
    drop constraint if exists jarvis_agent_tasks_attempts_check;
alter table public.jarvis_agent_tasks
    add constraint jarvis_agent_tasks_attempts_check
    check (attempts >= 0 and max_attempts between 1 and 20);

create unique index if not exists jarvis_agent_tasks_idempotency_idx
    on public.jarvis_agent_tasks(idempotency_key)
    where idempotency_key is not null;
create index if not exists jarvis_agent_tasks_priority_ready_idx
    on public.jarvis_agent_tasks(priority desc, created_at asc, task_id)
    where status = 'ready';

-- Claim the highest-priority eligible task in one transaction. SKIP LOCKED
-- lets concurrent agents claim different rows without waiting on one another.
create or replace function public.claim_next_jarvis_agent_task(
    p_agent_id text,
    p_lease_seconds integer default 90
)
returns setof public.jarvis_agent_tasks
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_task_id text;
    v_claimed public.jarvis_agent_tasks%rowtype;
    v_agent public.jarvis_agents%rowtype;
begin
    if p_agent_id is null or btrim(p_agent_id) = '' then
        raise exception 'p_agent_id must not be empty';
    end if;
    if p_lease_seconds < 10 or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    -- Lock the agent before a task to match the established claim function's
    -- lock order and avoid oversubscribing its concurrency limit.
    select * into v_agent
      from public.jarvis_agents
     where agent_id = p_agent_id
     for update;
    if not found
       or v_agent.status not in ('available', 'busy')
       or v_agent.active_tasks >= v_agent.concurrency_limit then
        return;
    end if;

    select t.task_id into v_task_id
      from public.jarvis_agent_tasks t
     where t.status = 'ready'
       and (t.parent_task_id is null or exists (
            select 1 from public.jarvis_agent_tasks parent
             where parent.task_id = t.parent_task_id and parent.status = 'completed'
       ))
       and v_agent.available_tools @> to_jsonb(t.required_tools)
     order by t.priority desc, t.created_at asc, t.task_id asc
     limit 1
     for update of t skip locked;

    if not found then
        return;
    end if;

    select * into v_claimed
      from public.claim_jarvis_agent_task(v_task_id, p_agent_id, p_lease_seconds);

    if not found then
        return;
    end if;

    update public.jarvis_agent_tasks
       set attempts = attempts + 1, updated_at = now()
     where task_id = v_task_id
     returning * into v_claimed;

    return next v_claimed;
end;
$$;

-- Requeue expired leases, while enforcing a finite retry budget.
create or replace function public.recover_expired_jarvis_agent_tasks()
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_candidate record;
    v_task public.jarvis_agent_tasks%rowtype;
    v_recovered integer := 0;
begin
    -- Discover candidates without locking task rows, then acquire locks in the
    -- same agent -> task order used by claim/finish operations.
    for v_candidate in
        select task_id, assigned_agent_id
          from public.jarvis_agent_tasks
         where status in ('claimed', 'in_progress', 'verifying')
           and lease_expires_at is not null
           and lease_expires_at <= now()
         order by lease_expires_at
         limit 100
    loop
        if v_candidate.assigned_agent_id is not null then
            perform 1 from public.jarvis_agents
             where agent_id = v_candidate.assigned_agent_id
             for update;
        end if;

        select * into v_task
          from public.jarvis_agent_tasks
         where task_id = v_candidate.task_id
           and status in ('claimed', 'in_progress', 'verifying')
           and lease_expires_at <= now()
         for update skip locked;
        if not found then
            continue;
        end if;

        update public.jarvis_agent_attempts
           set status = 'failed', finished_at = now(),
               error_summary = 'Lease expired before completion'
         where attempt_id = v_task.attempt_id
           and status in ('claimed', 'in_progress', 'verifying');

        update public.jarvis_agent_tasks
           set status = case when attempts >= max_attempts then 'failed' else 'ready' end,
               assigned_agent_id = null, attempt_id = null,
               lease_expires_at = null, updated_at = now()
         where task_id = v_task.task_id;

        if v_task.assigned_agent_id is not null then
            update public.jarvis_agents
               set active_tasks = greatest(active_tasks - 1, 0),
                   status = case
                       when status in ('offline', 'degraded') then status
                       when greatest(active_tasks - 1, 0) < concurrency_limit then 'available'
                       else 'busy'
                   end,
                   updated_at = now()
             where agent_id = v_task.assigned_agent_id;
        end if;

        insert into public.jarvis_agent_events(task_id, attempt_id, agent_id, event_type, payload)
        values (v_task.task_id, v_task.attempt_id, v_task.assigned_agent_id,
                'task.lease_expired',
                jsonb_build_object('attempts', v_task.attempts, 'max_attempts', v_task.max_attempts));

        v_recovered := v_recovered + 1;
    end loop;
    return v_recovered;
end;
$$;

alter table public.jarvis_routine_definitions enable row level security;
revoke all on public.jarvis_routine_definitions from anon, authenticated;
grant select, insert, update on public.jarvis_routine_definitions to service_role;
revoke all on function public.claim_next_jarvis_agent_task(text, integer) from public, anon, authenticated;
revoke all on function public.recover_expired_jarvis_agent_tasks() from public, anon, authenticated;
grant execute on function public.claim_next_jarvis_agent_task(text, integer) to service_role;
grant execute on function public.recover_expired_jarvis_agent_tasks() to service_role;
