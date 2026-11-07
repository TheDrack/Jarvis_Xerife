-- pgTAP regression tests for per-claim message fencing.
begin;
select plan(12);

select ok(
    position('claim_token = gen_random_uuid()' in
        pg_get_functiondef(
            'public.claim_jarvis_agent_message(text,integer)'::regprocedure
        )) > 0,
    'each message claim receives a fresh fencing token'
);
select ok(
    position('claim_token = p_claim_token' in
        pg_get_functiondef(
            'public.ack_jarvis_agent_message(uuid,text,uuid)'::regprocedure
        )) > 0,
    'ACK is fenced by the exact claim token'
);
select ok(
    not has_function_privilege(
        'service_role', 'public.ack_jarvis_agent_message(uuid,text)', 'EXECUTE'
    )
    and not has_function_privilege(
        'anon', 'public.ack_jarvis_agent_message(uuid,text)', 'EXECUTE'
    )
    and not has_function_privilege(
        'authenticated', 'public.ack_jarvis_agent_message(uuid,text)', 'EXECUTE'
    ),
    'legacy unfenced ACK overload is not executable'
);
select ok(
    has_function_privilege(
        'service_role', 'public.claim_jarvis_agent_message(text,integer)', 'EXECUTE'
    )
    and has_function_privilege(
        'service_role', 'public.ack_jarvis_agent_message(uuid,text,uuid)', 'EXECUTE'
    )
    and not has_function_privilege(
        'anon', 'public.claim_jarvis_agent_message(text,integer)', 'EXECUTE'
    )
    and not has_function_privilege(
        'authenticated', 'public.ack_jarvis_agent_message(uuid,text,uuid)', 'EXECUTE'
    ),
    'only service_role can execute the fenced queue RPCs'
);

do $null_lease$
begin
    perform 1 from public.claim_jarvis_agent_message('pgtap-worker', null);
    raise exception 'test expected the message claim to reject a NULL lease';
exception
    when others then
        if sqlerrm = 'test expected the message claim to reject a NULL lease' then
            raise;
        end if;
        if sqlerrm not like 'p_lease_seconds must be between 1 and 3600%' then
            raise;
        end if;
end
$null_lease$;
select pass('message claim rejects an explicit NULL lease duration');

insert into public.jarvis_agent_messages (
    message_id, task_id, sender_id, recipient_id, kind, payload
) values (
    '00000000-0000-0000-0000-000000000001',
    'pgtap-message-fencing-task',
    'pgtap-leader',
    'pgtap-worker',
    'request',
    '{}'::jsonb
);

create temp table first_claim as
select message_id, claim_token, lease_expires_at
  from public.claim_jarvis_agent_message('pgtap-worker', 5);

select is(
    (select count(*)::integer from first_claim),
    1,
    'first worker claim returns exactly one message'
);
select ok(
    (select claim_token is not null and lease_expires_at > now() from first_claim),
    'first claim includes a token and a live lease'
);

-- Simulate lease expiry without sleeping; the next claim must rotate the token.
update public.jarvis_agent_messages
   set lease_expires_at = now() - interval '1 second'
 where message_id = '00000000-0000-0000-0000-000000000001';

create temp table second_claim as
select message_id, claim_token
  from public.claim_jarvis_agent_message('pgtap-worker', 5);

select ok(
    (select first_claim.claim_token <> second_claim.claim_token
       from first_claim cross join second_claim),
    're-claim replaces the previous fencing token'
);
select is(
    public.ack_jarvis_agent_message(
        (select message_id from first_claim),
        'pgtap-worker',
        (select claim_token from first_claim)
    ),
    false,
    'stale worker cannot acknowledge a reclaimed message'
);
select is(
    public.ack_jarvis_agent_message(
        (select message_id from second_claim),
        'pgtap-worker',
        (select claim_token from second_claim)
    ),
    true,
    'current claim token can acknowledge the message'
);
select is(
    (select status from public.jarvis_agent_messages
      where message_id = '00000000-0000-0000-0000-000000000001'),
    'delivered',
    'successful fenced ACK marks the message delivered'
);
select ok(
    (select claim_token is null from public.jarvis_agent_messages
      where message_id = '00000000-0000-0000-0000-000000000001'),
    'successful ACK clears the claim token'
);

select * from finish();
rollback;
