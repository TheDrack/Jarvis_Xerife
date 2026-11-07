-- Supporting indexes for worker lease recovery and queue history.
begin;
select plan(5);
select ok(to_regclass('public.jarvis_agent_attempts_agent_id_idx') is not null,
    'attempt owner lookup is indexed');
select ok(to_regclass('public.jarvis_agent_attempts_task_id_idx') is not null,
    'attempt task lookup is indexed');
select ok(to_regclass('public.jarvis_agent_events_attempt_id_idx') is not null,
    'attempt event lookup is indexed');
select ok(to_regclass('public.jarvis_agent_tasks_parent_task_id_idx') is not null,
    'parent task lookup is indexed');
select ok(to_regclass('public.jarvis_agent_tasks_routine_id_idx') is not null,
    'routine task lookup is indexed');
select * from finish();
rollback;
