create or replace function public.rls_auto_enable()
returns event_trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    cmd record;
begin
    for cmd in
        select *
          from pg_event_trigger_ddl_commands()
         where command_tag in ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
           and object_type in ('table', 'partitioned table')
    loop
        if cmd.schema_name is not null
           and cmd.schema_name = 'public'
           and cmd.schema_name not in ('pg_catalog', 'information_schema')
           and cmd.schema_name not like 'pg_toast%'
           and cmd.schema_name not like 'pg_temp%' then
            execute format('alter table if exists %s enable row level security', cmd.object_identity);
        end if;
    end loop;
end;
$$;

create event trigger ensure_rls
    on ddl_command_end
    when tag in ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
    execute function public.rls_auto_enable();
