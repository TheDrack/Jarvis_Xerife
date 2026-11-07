-- Behavioral contract for the recurring intelligence worker lease.
begin;
select plan(10);

select ok(
    to_regclass('public.jarvis_intelligence_worker_lease') is not null
    and to_regclass('public.jarvis_intelligence_worker_runs') is not null
    and to_regclass('public.intelligence_event_snapshots') is not null
    and to_regclass('public.intelligence_observation_snapshots') is not null,
    'worker lease/run tables are installed beside the history tables'
);

select ok(
    has_function_privilege('service_role', 'public.claim_jarvis_intelligence_worker_lease(text,integer)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.renew_jarvis_intelligence_worker_lease(text,integer)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.release_jarvis_intelligence_worker_lease(text)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.record_jarvis_intelligence_worker_run(text,jsonb)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.get_jarvis_intelligence_history_metrics()', 'EXECUTE')
    and not has_function_privilege('anon', 'public.claim_jarvis_intelligence_worker_lease(text,integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_jarvis_intelligence_worker_lease(text,integer)', 'EXECUTE'),
    'worker RPCs are executable only by the trusted service role'
);

select is(
    public.claim_jarvis_intelligence_worker_lease('worker-one', 60),
    true,
    'first worker acquires the singleton lease'
);
select is(
    public.claim_jarvis_intelligence_worker_lease('worker-two', 60),
    false,
    'a competing worker cannot steal an unexpired lease'
);
select is(
    public.renew_jarvis_intelligence_worker_lease('worker-one', 60),
    true,
    'current owner renews the lease'
);
select is(
    public.record_jarvis_intelligence_worker_run(
        'worker-one',
        jsonb_build_object(
            'status', 'completed',
            'started_at_epoch', extract(epoch from now() - interval '2 seconds'),
            'finished_at_epoch', extract(epoch from now()),
            'duration_ms', 2000,
            'event_count', 4,
            'observation_count', 3,
            'retention_observation_days', 90,
            'history_metrics', jsonb_build_object('row_counts_are_estimates', true)
        )
    ),
    true,
    'current lease owner can append a completed run record'
);
select is(
    public.release_jarvis_intelligence_worker_lease('worker-one'),
    true,
    'current owner releases the singleton lease'
);
select is(
    public.renew_jarvis_intelligence_worker_lease('worker-one', 60),
    false,
    'released owner cannot renew the lease'
);
select is(
    (select status from public.jarvis_intelligence_worker_runs order by id desc limit 1),
    'completed',
    'worker run telemetry is persisted'
);
select ok(
    (public.get_jarvis_intelligence_history_metrics() ->> 'row_counts_are_estimates')::boolean,
    'history metrics explicitly identify catalog row counts as estimates'
);

select * from finish();
rollback;
