revoke all on table public.execution_plan_events from anon, authenticated, service_role;
grant select, insert on table public.execution_plan_events to service_role;