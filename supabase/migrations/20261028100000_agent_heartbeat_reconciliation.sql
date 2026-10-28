-- Reconcile stale agent presence during queue claims.
-- This is lazy reconciliation: every claim refreshes stale statuses and, more
-- importantly, a stale heartbeat can never be used to claim new work.
-- No task rows or history are deleted.

create or replace function public.mark_stale_jarvis_agents_offline(
    p_stale_after_seconds integer default 90
)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_updated integer := 0;
begin
    if p_stale_after_seconds is null
       or p_stale_after_seconds < 10
       or p_stale_after_seconds > 3600 then
        raise exception 'stale heartbeat threshold must be between 10 and 3600 seconds';
    end if;

    -- Lock in stable order and skip rows another concurrent reconciler owns.
    with stale_agents as (
        select agent_id
          from public.jarvis_agents
         where status in ('available', 'busy', 'degraded')
           and (last_seen_at is null
                or last_seen_at <= now() - make_interval(secs => p_stale_after_seconds))
         order by agent_id
         for update skip locked
    )
    update public.jarvis_agents as agents
       set status = 'offline',
           updated_at = now()
      from stale_agents
     where agents.agent_id = stale_agents.agent_id;

    get diagnostics v_updated = row_count;
    return v_updated;
end;
$$;

-- Replace the scheduler function without changing priority, tool eligibility,
-- parent dependency, lease, or attempt semantics.
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
    v_heartbeat_timeout integer;
begin
    if p_agent_id is null or btrim(p_agent_id) = '' then
        raise exception 'p_agent_id must not be empty';
    end if;
    if p_lease_seconds < 10 or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    -- A claim request also reconciles agents that stopped heartbeating.
    -- The timeout is at least 90s to tolerate short scheduling/network pauses.
    v_heartbeat_timeout := greatest(90, p_lease_seconds);
    perform public.mark_stale_jarvis_agents_offline(v_heartbeat_timeout);

    -- Keep the established agent -> task lock order.
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

revoke all on function public.mark_stale_jarvis_agents_offline(integer)
    from public, anon, authenticated;
grant execute on function public.mark_stale_jarvis_agents_offline(integer)
    to service_role;
revoke all on function public.claim_next_jarvis_agent_task(text, integer)
    from public, anon, authenticated;
grant execute on function public.claim_next_jarvis_agent_task(text, integer)
    to service_role;
