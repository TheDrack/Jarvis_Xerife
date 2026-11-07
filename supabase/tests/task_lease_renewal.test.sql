-- pgTAP tests for the task-worker lease renewal contract.
-- NULL must be rejected explicitly because PL/pgSQL IF treats a NULL predicate as not true.
begin;
select plan(11);

select ok(
    has_function_privilege(
        'service_role',
        'public.renew_jarvis_agent_task_lease(text,text,uuid,integer)',
        'EXECUTE'
    )
    and not has_function_privilege(
        'anon',
        'public.renew_jarvis_agent_task_lease(text,text,uuid,integer)',
        'EXECUTE'
    )
    and not has_function_privilege(
        'authenticated',
        'public.renew_jarvis_agent_task_lease(text,text,uuid,integer)',
        'EXECUTE'
    ),
    'only service_role can execute the task lease renewal RPC'
);

insert into public.jarvis_agent_tasks (
    task_id, objective, leader_id, assigned_agent_id, attempt_id, status, lease_expires_at
) values (
    'lease-renewal-test',
    'Verify lease renewal ownership and expiry',
    'lease-leader',
    'lease-worker',
    '11111111-1111-4111-8111-111111111111',
    'in_progress',
    now() + interval '60 seconds'
);

do $null_lease$
begin
    perform public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        null
    );
    raise exception 'test expected renewal to reject a NULL lease';
exception
    when others then
        if sqlerrm = 'test expected renewal to reject a NULL lease' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$null_lease$;
select pass('lease renewal rejects an explicit NULL duration');

select is(
    public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        120
    ),
    true,
    'current attempt can renew its active lease'
);
select ok(
    (select lease_expires_at >= now() + interval '119 seconds'
            and lease_expires_at <= now() + interval '121 seconds'
       from public.jarvis_agent_tasks
      where task_id = 'lease-renewal-test'),
    'renewal extends the lease by the requested duration'
);
select is(
    (select count(*)::integer from public.jarvis_agent_events
      where task_id = 'lease-renewal-test'
        and event_type = 'task.lease_renewed'),
    1,
    'successful renewal appends one audit event'
);

select is(
    public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '22222222-2222-4222-8222-222222222222',
        120
    ),
    false,
    'a different attempt cannot renew the task lease'
);

update public.jarvis_agent_tasks
   set lease_expires_at = now() - interval '1 second'
 where task_id = 'lease-renewal-test';
select is(
    public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        120
    ),
    false,
    'an expired lease cannot be resurrected'
);

update public.jarvis_agent_tasks
   set status = 'completed',
       lease_expires_at = now() + interval '60 seconds'
 where task_id = 'lease-renewal-test';
select is(
    public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        120
    ),
    false,
    'completed tasks cannot have their lease renewed'
);
select is(
    (select count(*)::integer from public.jarvis_agent_events
      where task_id = 'lease-renewal-test'
        and event_type = 'task.lease_renewed'),
    1,
    'rejected renewal attempts do not append audit events'
);

do $short_lease$
begin
    perform public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        9
    );
    raise exception 'test expected renewal to reject a short lease';
exception
    when others then
        if sqlerrm = 'test expected renewal to reject a short lease' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$short_lease$;
select pass('lease renewal rejects durations below the supported minimum');

do $long_lease$
begin
    perform public.renew_jarvis_agent_task_lease(
        'lease-renewal-test',
        'lease-worker',
        '11111111-1111-4111-8111-111111111111',
        3601
    );
    raise exception 'test expected renewal to reject a long lease';
exception
    when others then
        if sqlerrm = 'test expected renewal to reject a long lease' then
            raise;
        end if;
        if sqlerrm not like 'lease duration must be between 10 and 3600 seconds%' then
            raise;
        end if;
end
$long_lease$;
select pass('lease renewal rejects durations above the supported maximum');

select * from finish();
rollback;
