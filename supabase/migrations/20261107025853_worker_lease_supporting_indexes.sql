-- Supporting indexes for task lease recovery and worker audit lookups.
-- The historical lease RPC is defined by the later NULL-safe migration.
create index if not exists jarvis_agent_attempts_agent_id_idx
    on public.jarvis_agent_attempts (agent_id);
create index if not exists jarvis_agent_attempts_task_id_idx
    on public.jarvis_agent_attempts (task_id);
create index if not exists jarvis_agent_events_attempt_id_idx
    on public.jarvis_agent_events (attempt_id);
create index if not exists jarvis_agent_tasks_parent_task_id_idx
    on public.jarvis_agent_tasks (parent_task_id);
create index if not exists jarvis_agent_tasks_routine_id_idx
    on public.jarvis_agent_tasks (routine_id);
