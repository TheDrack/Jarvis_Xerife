-- Reject NULL lease durations explicitly. In PostgreSQL, a comparison with
-- NULL yields NULL, so "< 10 OR > 3600" alone does not enforce this bound.
-- This forward-only migration preserves the existing task ownership, status,
-- expiry, audit event, and service-role access semantics.

create or replace function public.renew_jarvis_agent_task_lease(
    p_task_id text,
    p_agent_id text,
    p_attempt_id uuid,
    p_lease_seconds integer default 90
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_updated integer;
begin
    if p_task_id is null or btrim(p_task_id) = ''
       or p_agent_id is null or btrim(p_agent_id) = '' then
        raise exception 'task and agent identifiers must not be empty';
    end if;
    if p_lease_seconds is null
       or p_lease_seconds < 10
       or p_lease_seconds > 3600 then
        raise exception 'lease duration must be between 10 and 3600 seconds';
    end if;

    update public.jarvis_agent_tasks
       set lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           updated_at = now()
     where task_id = p_task_id
       and assigned_agent_id = p_agent_id
       and attempt_id = p_attempt_id
       and status in ('claimed', 'in_progress', 'verifying')
       and lease_expires_at > now();

    get diagnostics v_updated = row_count;
    if v_updated = 0 then
        return false;
    end if;

    insert into public.jarvis_agent_events(task_id, attempt_id, agent_id, event_type, payload)
    values (p_task_id, p_attempt_id, p_agent_id, 'task.lease_renewed',
            jsonb_build_object('lease_seconds', p_lease_seconds));
    return true;
end;
$$;

revoke all on function public.renew_jarvis_agent_task_lease(text, text, uuid, integer)
    from public, anon, authenticated;
grant execute on function public.renew_jarvis_agent_task_lease(text, text, uuid, integer)
    to service_role;
