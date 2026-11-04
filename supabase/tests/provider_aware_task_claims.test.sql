-- Regression tests for provider-aware multi-agent task claims.
-- Run with pgTAP after applying 20261104235000_provider_aware_remote_task_claims.
begin;
select plan(7);

select ok(
    position(
        'lower(replace(replace(v_task.task_type' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)
    ) > 0
    and position(
        'lower(btrim(coalesce(v_agent.model_provider' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)
    ) > 0,
    'direct task claims enforce Venice for Red/Blue task types'
);

select ok(
    position(
        'lower(replace(replace(t.task_type' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)
    ) > 0
    and position(
        'lower(btrim(coalesce(v_agent.model_provider' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)
    ) > 0,
    'queue claims filter Red/Blue tasks by the agent provider'
);

select ok(
    position('for update of t skip locked' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)
    ) > 0,
    'queue claims retain SKIP LOCKED for concurrent workers'
);

select ok(
    position('fencing_token = t.fencing_token + 1' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)
    ) > 0,
    'direct claims retain monotonically increasing fencing tokens'
);

select ok(
    position('make_interval(secs => p_lease_seconds)' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)
    ) > 0,
    'direct claims retain lease expiration'
);

select ok(
    not exists (
        select 1
        from pg_proc p
        cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
        where p.oid in (
            'public.claim_jarvis_agent_task(text,text,integer)'::regprocedure,
            'public.claim_next_jarvis_agent_task(text,integer)'::regprocedure
        )
          and acl.grantee = 0
          and acl.privilege_type = 'EXECUTE'
    )
    and not has_function_privilege('anon', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE'),
    'claim RPCs are not executable by public or client roles'
);

select ok(
    has_function_privilege('service_role', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE'),
    'trusted service_role retains execute on both claim RPCs'
);

select * from finish();
rollback;
