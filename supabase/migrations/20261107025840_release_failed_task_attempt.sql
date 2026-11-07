-- Immediate release for a failed task attempt.
-- Apply only after reviewing against the target Supabase project.
--
-- Until now a worker that failed mid-task left its claim in place until the lease
-- expired (90 seconds by default), so another agent could only pick the task up
-- after that wait. This function hands the task back at once, keeps the retry
-- budget honest, and refuses anything that is not the current owner attempt.

create or replace function public.release_jarvis_agent_task(
    p_task_id text,
    p_agent_id text,
    p_attempt_id uuid,
    p_reason text default 'worker error'
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_task public.jarvis_agent_tasks%rowtype;
    v_reason text;
begin
    if p_task_id is null or btrim(p_task_id) = ''
       or p_agent_id is null or btrim(p_agent_id) = '' then
        raise exception 'task and agent identifiers must not be empty';
    end if;

    v_reason := left(coalesce(nullif(btrim(p_reason), ''), 'worker error'), 500);

    -- Same lock order as claim/finish (agent first, then task) so a release
    -- cannot deadlock with a concurrent claim or completion.
    perform 1 from public.jarvis_agents
     where agent_id = p_agent_id
     for update;
    if not found then
        return false;
    end if;

    select * into v_task
      from public.jarvis_agent_tasks
     where task_id = p_task_id
       and assigned_agent_id = p_agent_id
       and attempt_id = p_attempt_id
       and status in ('claimed', 'in_progress', 'verifying')
     for update;
    if not found then
        -- Stale or foreign attempt: the lease/recovery path owns it.
        return false;
    end if;

    update public.jarvis_agent_attempts
       set status = 'failed',
           finished_at = now(),
           error_summary = v_reason
     where attempt_id = p_attempt_id
       and task_id = p_task_id
       and agent_id = p_agent_id
       and status in ('claimed', 'in_progress', 'verifying');

    update public.jarvis_agent_tasks
       set status = case when attempts >= max_attempts then 'failed' else 'ready' end,
           assigned_agent_id = null,
           attempt_id = null,
           lease_expires_at = null,
           updated_at = now()
     where task_id = p_task_id;

    update public.jarvis_agents
       set active_tasks = greatest(active_tasks - 1, 0),
           status = case
               when status in ('offline', 'degraded') then status
               when greatest(active_tasks - 1, 0) < concurrency_limit then 'available'
               else 'busy'
           end,
           updated_at = now()
     where agent_id = p_agent_id;

    insert into public.jarvis_agent_events(task_id, attempt_id, agent_id, event_type, payload)
    values (p_task_id, p_attempt_id, p_agent_id, 'task.released',
            jsonb_build_object('reason', v_reason,
                               'attempts', v_task.attempts,
                               'max_attempts', v_task.max_attempts));

    return true;
end;
$$;

revoke all on function public.release_jarvis_agent_task(text, text, uuid, text)
    from public, anon, authenticated;
grant execute on function public.release_jarvis_agent_task(text, text, uuid, text)
    to service_role;
