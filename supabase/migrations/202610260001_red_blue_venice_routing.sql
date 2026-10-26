-- Role-aware provider routing for Red Team / Blue Team tasks.
-- Existing agents default to unknown and cannot claim protected tasks until
-- their runtime advertises the provider it actually uses.
alter table public.jarvis_agents
    add column if not exists model_provider text not null default 'unknown';

-- Defense in depth: direct claims cannot bypass the role/provider policy.
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

    select * into v_task
      from public.jarvis_agent_tasks
     where task_id = p_task_id
       and status = 'ready'
     for update;

    if not found then
        return;
    end if;

    if lower(replace(replace(v_task.task_type, '-', '_'), ' ', '_')) in ('red_team', 'blue_team')
       and lower(coalesce(v_agent.model_provider, 'unknown')) <> 'venice' then
        return;
    end if;

    if not (v_agent.available_tools @> to_jsonb(v_task.required_tools)) then
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
       and (t.assigned_agent_id is null or t.assigned_agent_id = p_agent_id)
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
                           'lease_expires_at', v_task.lease_expires_at,
                           'model_provider', v_agent.model_provider)
    );

    return next v_task;
end;
$$;

-- Claim only tasks eligible for this agent's actual advertised provider.
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
       and (
           lower(replace(replace(t.task_type, '-', '_'), ' ', '_')) not in ('red_team', 'blue_team')
           or lower(coalesce(v_agent.model_provider, 'unknown')) = 'venice'
       )
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

revoke all on function public.claim_jarvis_agent_task(text, text, integer) from public, anon, authenticated;
revoke all on function public.claim_next_jarvis_agent_task(text, integer) from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_task(text, text, integer) to service_role;
grant execute on function public.claim_next_jarvis_agent_task(text, integer) to service_role;
