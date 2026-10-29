-- Tighten privileges after the initial environment-observations table was deployed.
revoke all on table public.jarvis_environment_observations
    from public, anon, authenticated, service_role;
grant select, insert on table public.jarvis_environment_observations to service_role;
