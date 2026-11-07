-- Persist the authenticated creator and owner independently from the worker executor.
-- Existing rows remain NULL (legacy/internal tasks and global routines).

alter table public.jarvis_agent_tasks
    add column if not exists created_by text,
    add column if not exists owner_id text;

alter table public.jarvis_routine_definitions
    add column if not exists created_by text,
    add column if not exists owner_id text;

do $$
begin
    if not exists (
        select 1 from pg_constraint
         where conname = 'jarvis_agent_tasks_created_by_length_check'
           and conrelid = 'public.jarvis_agent_tasks'::regclass
    ) then
        alter table public.jarvis_agent_tasks
            add constraint jarvis_agent_tasks_created_by_length_check
            check (created_by is null or length(btrim(created_by)) between 1 and 200);
    end if;

    if not exists (
        select 1 from pg_constraint
         where conname = 'jarvis_agent_tasks_owner_id_length_check'
           and conrelid = 'public.jarvis_agent_tasks'::regclass
    ) then
        alter table public.jarvis_agent_tasks
            add constraint jarvis_agent_tasks_owner_id_length_check
            check (owner_id is null or length(btrim(owner_id)) between 1 and 200);
    end if;

    if not exists (
        select 1 from pg_constraint
         where conname = 'jarvis_routine_definitions_created_by_length_check'
           and conrelid = 'public.jarvis_routine_definitions'::regclass
    ) then
        alter table public.jarvis_routine_definitions
            add constraint jarvis_routine_definitions_created_by_length_check
            check (created_by is null or length(btrim(created_by)) between 1 and 200);
    end if;

    if not exists (
        select 1 from pg_constraint
         where conname = 'jarvis_routine_definitions_owner_id_length_check'
           and conrelid = 'public.jarvis_routine_definitions'::regclass
    ) then
        alter table public.jarvis_routine_definitions
            add constraint jarvis_routine_definitions_owner_id_length_check
            check (owner_id is null or length(btrim(owner_id)) between 1 and 200);
    end if;
end
$$;

create index if not exists jarvis_agent_tasks_owner_status_created_idx
    on public.jarvis_agent_tasks (owner_id, status, created_at desc)
    where owner_id is not null;

create index if not exists jarvis_routine_definitions_owner_key_idx
    on public.jarvis_routine_definitions (owner_id, routine_key)
    where owner_id is not null;

comment on column public.jarvis_agent_tasks.created_by is
    'Authenticated principal that submitted the task; independent from the executing agent.';
comment on column public.jarvis_agent_tasks.owner_id is
    'User or context that owns the task and receives owner-scoped notifications.';
comment on column public.jarvis_routine_definitions.created_by is
    'Authenticated principal that created the routine definition.';
comment on column public.jarvis_routine_definitions.owner_id is
    'Owner allowed to update and trigger this routine; NULL denotes a shared legacy/system routine.';
