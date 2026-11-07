-- Current-attempt release behavior and worker accounting.
begin;
select plan(9);

select ok(
    has_function_privilege('service_role', 'public.release_jarvis_agent_task(text,text,uuid,text)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.release_jarvis_agent_task(text,text,uuid,text)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.release_jarvis_agent_task(text,text,uuid,text)', 'EXECUTE'),
    'release RPC is restricted to service_role'
);

insert into public.jarvis_agents (
    agent_id, runtime_version, environment, available_tools, status,
    active_tasks, concurrency_limit, last_seen_at
) values (
    'release-worker', 'pgTAP', 'ci', '[]'::jsonb, 'busy', 1, 2, now()
);

insert into public.jarvis_agent_tasks (
    task_id, objective, leader_id, task_type, required_tools,
    constraints, acceptance_criteria, status, attempts, max_attempts,
    assigned_agent_id, attempt_id, lease_expires_at
) values (
    'release-test-task',
    'Verify failed attempt release',
    'release-test-leader',
    'release_test',
    array['text_reasoning'],
    '[]'::jsonb,
    '[]'::jsonb,
    'in_progress',
    1,
    3,
    'release-worker',
    '22222222-2222-4222-8222-222222222222',
    now() + interval '60 seconds'
);

insert into public.jarvis_agent_attempts (
    attempt_id, task_id, agent_id, assigned_role, status
) values (
    '22222222-2222-4222-8222-222222222222',
    'release-test-task',
    'release-worker',
    'worker',
    'in_progress'
);

select is(
    public.release_jarvis_agent_task(
        'release-test-task',
        'release-worker',
        '22222222-2222-4222-8222-222222222222',
        'simulated provider failure'
    ),
    true,
    'current owner can release its failed attempt'
);
select is(
    (select status from public.jarvis_agent_tasks where task_id = 'release-test-task'),
    'ready',
    'task returns to ready while retry budget remains'
);
select is(
    (select assigned_agent_id from public.jarvis_agent_tasks where task_id = 'release-test-task'),
    null::text,
    'released task no longer belongs to the failed worker'
);
select ok(
    (select attempt_id is null and lease_expires_at is null
       from public.jarvis_agent_tasks where task_id = 'release-test-task'),
    'released task clears attempt fencing and lease'
);
select ok(
    (select status = 'failed' and error_summary = 'simulated provider failure'
       from public.jarvis_agent_attempts
      where attempt_id = '22222222-2222-4222-8222-222222222222'),
    'failed attempt is closed with its reason'
);
select ok(
    (select active_tasks = 0 and status = 'available'
       from public.jarvis_agents where agent_id = 'release-worker'),
    'worker active-task accounting is restored'
);
select ok(
    exists (
        select 1 from public.jarvis_agent_events
         where task_id = 'release-test-task'
           and attempt_id = '22222222-2222-4222-8222-222222222222'
           and event_type = 'task.released'
           and payload->>'reason' = 'simulated provider failure'
    ),
    'release emits an auditable event'
);
select is(
    public.release_jarvis_agent_task(
        'release-test-task',
        'release-worker',
        '22222222-2222-4222-8222-222222222222',
        'stale retry'
    ),
    false,
    'a stale attempt cannot release the task again'
);

select * from finish();
rollback;
