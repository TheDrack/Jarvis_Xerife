-- Enforce parent-task dependencies in the direct claim RPC as well as queue selection.
-- The queue RPC already rejects children until their parent is completed, but
-- SupabaseAgentStore.claim_task calls this direct RPC and could bypass that gate.
-- Forward-only: no existing task or agent rows are rewritten.

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
    v_heartbeat_timeout integer;
begin
    if p_lease_seconds is null or p_lease_seconds < 10 or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    v_heartbeat_timeout := greatest(90, p_lease_seconds);

    select * into v_agent
      from public.jarvis_agents
     where agent_id = p_agent_id
     for update;

    if not found
       or v_agent.status not in ('available', 'busy')
       or v_agent.last_seen_at is null
       or v_agent.last_seen_at <= now() - make_interval(secs => v_heartbeat_timeout)
       or v_agent.active_tasks >= v_agent.concurrency_limit then
        return;
    end if;

    select task.* into v_task
      from public.jarvis_agent_tasks as task
     where task.task_id = p_task_id
       and task.status = 'ready'
       and (task.assigned_agent_id is null or task.assigned_agent_id = p_agent_id)
       and (
           task.parent_task_id is null
           or exists (
               select 1
                 from public.jarvis_agent_tasks as parent
                where parent.task_id = task.parent_task_id
                  and parent.status = 'completed'
           )
       )
     for update of task;

    if not found then
        return;
    end if;

    -- Direct claims must enforce the same provider policy as queue selection.
    if lower(replace(replace(v_task.task_type, '-', '_'), ' ', '_')) in ('red_team', 'blue_team')
       and lower(btrim(coalesce(v_agent.model_provider, 'unknown'))) <> 'venice' then
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
       and (
           t.parent_task_id is null
           or exists (
               select 1
                 from public.jarvis_agent_tasks as parent
                where parent.task_id = t.parent_task_id
                  and parent.status = 'completed'
           )
       )
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

revoke all on function public.claim_jarvis_agent_task(text, text, integer) from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_task(text, text, integer) to service_role;
