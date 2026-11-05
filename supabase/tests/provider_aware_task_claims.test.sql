-- Regression tests for provider-aware multi-agent task claims.
-- This file is executed only against an isolated local Supabase database.
begin;
select plan(32);

select ok(
    position('lower(replace(replace(v_task.task_type' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0
    and position('lower(btrim(coalesce(v_agent.model_provider' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0,
    'direct task claims enforce Venice for Red/Blue task types'
);
select ok(
    position('lower(replace(replace(t.task_type' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)) > 0
    and position('lower(btrim(coalesce(v_agent.model_provider' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)) > 0,
    'queue claims filter Red/Blue tasks by the agent provider'
);
select ok(
    position('last_seen_at' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0
    and position('v_heartbeat_timeout' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0,
    'direct claims reject agents with stale or missing heartbeats'
);

select ok(
    position('mark_stale_jarvis_agents_offline' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)) > 0
    and position('last_seen_at' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)) > 0,
    'queue claims reconcile stale agent heartbeats before assigning work'
);

select ok(
    position('for update of t skip locked' in
        pg_get_functiondef('public.claim_next_jarvis_agent_task(text,integer)'::regprocedure)) > 0,
    'queue claims retain SKIP LOCKED for concurrent workers'
);
select ok(
    position('fencing_token = t.fencing_token + 1' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0,
    'direct claims retain monotonically increasing fencing tokens'
);
select ok(
    position('make_interval(secs => p_lease_seconds)' in
        pg_get_functiondef('public.claim_jarvis_agent_task(text,text,integer)'::regprocedure)) > 0,
    'direct claims retain lease expiration'
);
select ok(
    not exists (
        select 1
        from pg_proc p
        cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
        where p.oid in (
            'public.claim_jarvis_agent_task(text,text,integer)'::regprocedure,
            'public.claim_next_jarvis_agent_task(text,integer)'::regprocedure,
            'public.mark_stale_jarvis_agents_offline(integer)'::regprocedure
        )
          and acl.grantee = 0
          and acl.privilege_type = 'EXECUTE'
    )
    and not has_function_privilege('anon', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE')
    and not has_function_privilege('anon', 'public.mark_stale_jarvis_agents_offline(integer)', 'EXECUTE')
    and not has_function_privilege('authenticated', 'public.mark_stale_jarvis_agents_offline(integer)', 'EXECUTE'),
    'claim RPCs are not executable by PUBLIC or client roles'
);
select ok(
    has_function_privilege('service_role', 'public.claim_jarvis_agent_task(text,text,integer)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.claim_next_jarvis_agent_task(text,integer)', 'EXECUTE')
    and has_function_privilege('service_role', 'public.mark_stale_jarvis_agents_offline(integer)', 'EXECUTE'),
    'trusted service_role retains execute on both claim RPCs'
);

insert into public.jarvis_agents (
    agent_id, runtime_version, environment, available_tools, status,
    active_tasks, concurrency_limit, model_provider, last_seen_at
) values
    ('pgtap-direct-openai', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'openai', now()),
    ('pgtap-direct-venice', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, ' VeNiCe ', now()),
    ('pgtap-queue-unknown', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'unknown', now()),
    ('pgtap-queue-venice', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'VENICE', now()),
    ('pgtap-parent-venice', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'venice', now()),
    ('pgtap-tools-venice', 'pgtap', 'ci', '["read"]'::jsonb, 'available', 0, 2, 'venice', now());

insert into public.jarvis_agent_tasks (
    task_id, objective, task_type, required_tools, status, leader_id,
    assigned_agent_id, priority
) values
    ('pgtap-direct-openai-task', 'provider guard test', 'red-team', '{}', 'ready', 'pgtap', 'pgtap-direct-openai', 100),
    ('pgtap-direct-venice-task', 'provider allow test', 'Red-Team', '{}', 'ready', 'pgtap', 'pgtap-direct-venice', 100),
    ('pgtap-queue-unknown-task', 'queue provider guard test', 'blue_team', '{}', 'ready', 'pgtap', 'pgtap-queue-unknown', 100),
    ('pgtap-queue-venice-task', 'queue provider allow test', 'Blue Team', '{}', 'ready', 'pgtap', 'pgtap-queue-venice', 100),
    ('pgtap-parent-task', 'parent dependency fixture', 'general', '{}', 'in_progress', 'pgtap', null, 100),
    ('pgtap-child-task', 'queue parent dependency test', 'red_team', '{}', 'ready', 'pgtap', 'pgtap-parent-venice', 100),
    ('pgtap-direct-child-task', 'direct parent dependency test', 'red_team', '{}', 'ready', 'pgtap', 'pgtap-parent-venice', 101);

update public.jarvis_agent_tasks
   set parent_task_id = 'pgtap-parent-task'
 where task_id in ('pgtap-child-task', 'pgtap-direct-child-task');

insert into public.jarvis_agent_tasks (
    task_id, objective, task_type, required_tools, status, leader_id,
    assigned_agent_id, priority
) values (
    'pgtap-tools-task', 'required tools guard test', 'general',
    array['write'], 'ready', 'pgtap', 'pgtap-tools-venice', 100
);


select is(
    (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-direct-openai-task', 'pgtap-direct-openai', 60)),
    0,
    'direct Red Team claim is rejected for a non-Venice provider'
);
select ok(
    (select status = 'ready' from public.jarvis_agent_tasks where task_id = 'pgtap-direct-openai-task')
    and (select active_tasks = 0 from public.jarvis_agents where agent_id = 'pgtap-direct-openai'),
    'rejected direct claim leaves task and agent state unchanged'
);
select is(
    (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-direct-venice-task', 'pgtap-direct-venice', 60)),
    1,
    'direct Red Team claim accepts a normalized Venice provider'
);
select ok(
    (select fencing_token = 1
            and lease_expires_at > now()
            and lease_expires_at <= now() + interval '60 seconds'
       from public.jarvis_agent_tasks where task_id = 'pgtap-direct-venice-task'),
    'direct claim preserves fencing token and requested lease duration'
);
select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-queue-unknown', 60)),
    0,
    'queue rejects Blue Team tasks for unknown providers'
);
select ok(
    (select status = 'ready' from public.jarvis_agent_tasks where task_id = 'pgtap-queue-unknown-task')
    and (select active_tasks = 0 from public.jarvis_agents where agent_id = 'pgtap-queue-unknown'),
    'rejected queue claim does not mutate task or agent state'
);
select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-queue-venice', 60)),
    1,
    'queue accepts Blue Team tasks for a normalized Venice provider'
);
select ok(
    (select status = 'claimed' and attempts = 1 and fencing_token = 1
       from public.jarvis_agent_tasks where task_id = 'pgtap-queue-venice-task'),
    'queue claim increments attempts and fencing token exactly once'
);
select is(
    (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-direct-child-task', 'pgtap-parent-venice', 60)),
    0,
    'direct claim rejects a child while its parent is incomplete'
);
select ok(
    (select status = 'ready' from public.jarvis_agent_tasks where task_id = 'pgtap-direct-child-task')
    and (select active_tasks = 0 from public.jarvis_agents where agent_id = 'pgtap-parent-venice'),
    'rejected direct child claim leaves task and agent state unchanged'
);
select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-parent-venice', 60)),
    0,
    'queue does not claim a child while its parent is incomplete'
);
update public.jarvis_agent_tasks
   set status = 'completed'
 where task_id = 'pgtap-parent-task';
select is(
    (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-direct-child-task', 'pgtap-parent-venice', 60)),
    1,
    'direct claim accepts a child after its parent is completed'
);
select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-parent-venice', 60)),
    1,
    'queue claims the child after its parent is completed'
);
select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-tools-venice', 60)),
    0,
    'queue rejects tasks whose required tools are unavailable'
);
insert into public.jarvis_agents (
    agent_id, runtime_version, environment, available_tools, status,
    active_tasks, concurrency_limit, model_provider, last_seen_at
) values
    ('pgtap-stale-venice', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'venice', now() - interval '1 hour'),
    ('pgtap-null-heartbeat', 'pgtap', 'ci', '[]'::jsonb, 'available', 0, 2, 'venice', null);

insert into public.jarvis_agent_tasks (
    task_id, objective, task_type, required_tools, status, leader_id,
    assigned_agent_id, priority
) values
    ('pgtap-stale-heartbeat-task', 'stale heartbeat guard test', 'general', '{}', 'ready', 'pgtap', 'pgtap-stale-venice', 100),
    ('pgtap-null-heartbeat-task', 'missing heartbeat guard test', 'general', '{}', 'ready', 'pgtap', 'pgtap-null-heartbeat', 100);

select ok(
    (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-stale-heartbeat-task', 'pgtap-stale-venice', 60)) = 0
    and (select count(*)::integer from public.claim_jarvis_agent_task(
        'pgtap-null-heartbeat-task', 'pgtap-null-heartbeat', 60)) = 0
    and (select status = 'available' from public.jarvis_agents where agent_id = 'pgtap-stale-venice')
    and (select status = 'available' from public.jarvis_agents where agent_id = 'pgtap-null-heartbeat')
    and (select status = 'ready' from public.jarvis_agent_tasks where task_id = 'pgtap-stale-heartbeat-task')
    and (select status = 'ready' from public.jarvis_agent_tasks where task_id = 'pgtap-null-heartbeat-task'),
    'direct claims reject stale and missing heartbeats without mutating state'
);

select is(
    (select count(*)::integer from public.claim_next_jarvis_agent_task('pgtap-stale-venice', 60)),
    0,
    'queue does not claim work for an agent with an expired heartbeat'
);
select is(
    (select status from public.jarvis_agents where agent_id = 'pgtap-stale-venice'),
    'offline',
    'expired heartbeat transitions the stale agent to offline'
);
select is(
    (select status from public.jarvis_agents where agent_id = 'pgtap-null-heartbeat'),
    'offline',
    'missing heartbeat transitions the agent to offline'
);
select is(
    (select status from public.jarvis_agent_tasks where task_id = 'pgtap-stale-heartbeat-task'),
    'ready',
    'stale agent task remains available after rejected claim'
);
select is(
    (select status from public.jarvis_agent_tasks where task_id = 'pgtap-null-heartbeat-task'),
    'ready',
    'missing-heartbeat agent task remains available after rejected claim'
);

do $lease_test$
begin
    perform 1 from public.claim_jarvis_agent_task('missing-task', 'missing-agent', 9);
    raise exception 'test expected the lease duration check to reject the call';
exception
    when others then
        if sqlerrm = 'test expected the lease duration check to reject the call' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$lease_test$;
select pass('claim RPC rejects lease durations outside the supported bounds');

do $direct_null_lease$
begin
    perform 1 from public.claim_jarvis_agent_task('missing-task', 'missing-agent', null);
    raise exception 'test expected the direct claim to reject a NULL lease';
exception
    when others then
        if sqlerrm = 'test expected the direct claim to reject a NULL lease' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$direct_null_lease$;
select pass('direct claim rejects an explicit NULL lease duration');

do $queue_null_lease$
begin
    perform 1 from public.claim_next_jarvis_agent_task('missing-agent', null);
    raise exception 'test expected the queue claim to reject a NULL lease';
exception
    when others then
        if sqlerrm = 'test expected the queue claim to reject a NULL lease' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$queue_null_lease$;
select pass('queue claim rejects an explicit NULL lease duration');

select * from finish();
rollback;
