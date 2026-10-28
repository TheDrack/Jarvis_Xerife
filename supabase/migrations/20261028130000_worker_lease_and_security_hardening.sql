-- Harden internal queue tables and prevent healthy long-running inference from
-- losing its claim while the model provider is still responding.
-- Service-role access is preserved; no client-facing policies are granted.

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
    if p_lease_seconds < 10 or p_lease_seconds > 3600 then
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

-- Cover foreign keys used by recovery, task ancestry, and audit lookups.
create index if not exists jarvis_agent_attempts_agent_id_idx
    on public.jarvis_agent_attempts(agent_id);
create index if not exists jarvis_agent_attempts_task_id_idx
    on public.jarvis_agent_attempts(task_id);
create index if not exists jarvis_agent_events_attempt_id_idx
    on public.jarvis_agent_events(attempt_id);
create index if not exists jarvis_agent_tasks_parent_task_id_idx
    on public.jarvis_agent_tasks(parent_task_id);
create index if not exists jarvis_agent_tasks_routine_id_idx
    on public.jarvis_agent_tasks(routine_id);

-- These tables are internal control-plane data. RLS with no policies already
-- denies API row access; make that denial explicit and remove unused client grants.
do $$
declare
    v_table text;
    v_tables text[] := array[
        'evolution_rewards',
        'execution_plan_events',
        'jarvis_agent_attempts',
        'jarvis_agent_events',
        'jarvis_agent_messages',
        'jarvis_agent_tasks',
        'jarvis_agents',
        'jarvis_external_identities',
        'jarvis_mobile_device_sessions',
        'jarvis_mobile_push_devices',
        'jarvis_mobile_push_events',
        'jarvis_recovery_actions',
        'jarvis_recovery_checkpoints',
        'jarvis_recovery_events',
        'jarvis_recovery_runs',
        'jarvis_routine_definitions'
    ];
begin
    foreach v_table in array v_tables loop
        execute format('revoke all on table public.%I from anon, authenticated', v_table);
        if not exists (
            select 1 from pg_policies
             where schemaname = 'public'
               and tablename = v_table
               and policyname = 'jarvis_deny_api_roles'
        ) then
            execute format(
                'create policy jarvis_deny_api_roles on public.%I for all to anon, authenticated using (false) with check (false)',
                v_table
            );
        end if;
    end loop;
end;
$$;
