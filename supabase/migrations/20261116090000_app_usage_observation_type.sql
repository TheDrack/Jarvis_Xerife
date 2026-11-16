-- Extend the observation type allowlist without changing the JSONB payload schema.
-- location_snapshot is included because the API already supports that mobile observation.
alter table public.jarvis_environment_observations
    drop constraint if exists jarvis_environment_observations_observation_type_check;

alter table public.jarvis_environment_observations
    add constraint jarvis_environment_observations_observation_type_check
    check (observation_type in (
        'network_snapshot',
        'presence',
        'location_snapshot',
        'app_usage_snapshot'
    ));
