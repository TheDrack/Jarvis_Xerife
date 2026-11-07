-- Fence message acknowledgements to the exact queue claim attempt.
-- An agent_id can be reused after a worker restart; it is not an attempt token.
-- Apply only after reconciling the existing remote migration history.

alter table public.jarvis_agent_messages
    add column if not exists claim_token uuid;

-- Existing in-flight claims receive a token before the invariant is enforced.
update public.jarvis_agent_messages
   set claim_token = gen_random_uuid()
 where status = 'claimed'
   and claim_token is null;

alter table public.jarvis_agent_messages
    drop constraint if exists jarvis_message_claim_token_consistency;

alter table public.jarvis_agent_messages
    add constraint jarvis_message_claim_token_consistency
    check (
        (status = 'claimed' and claim_token is not null)
        or (status <> 'claimed' and claim_token is null)
    ) not valid;

alter table public.jarvis_agent_messages
    validate constraint jarvis_message_claim_token_consistency;

create or replace function public.claim_jarvis_agent_message(
    p_agent_id text,
    p_lease_seconds integer default 60
)
returns setof public.jarvis_agent_messages
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_message_id uuid;
begin
    if p_agent_id is null or btrim(p_agent_id) = '' then
        raise exception 'p_agent_id must not be empty';
    end if;
    if p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 3600 then
        raise exception 'p_lease_seconds must be between 1 and 3600';
    end if;

    select m.message_id into v_message_id
      from public.jarvis_agent_messages as m
     where m.recipient_id = p_agent_id
       and (m.status = 'pending'
            or (m.status = 'claimed' and m.lease_expires_at <= now()))
     order by m.created_at, m.message_id
     for update skip locked
     limit 1;

    if not found then
        return;
    end if;

    return query
    update public.jarvis_agent_messages as m
       set status = 'claimed',
           claimed_by = p_agent_id,
           claimed_at = now(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           delivery_attempts = m.delivery_attempts + 1,
           claim_token = gen_random_uuid()
     where m.message_id = v_message_id
    returning m.*;
end;
$$;

-- Remove the old unfenced ACK entry point. Leaving it executable would allow
-- callers to bypass the token check through the two-argument overload.
revoke all on function public.ack_jarvis_agent_message(uuid, text)
    from public, anon, authenticated, service_role;

create or replace function public.ack_jarvis_agent_message(
    p_message_id uuid,
    p_agent_id text,
    p_claim_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_updated integer;
begin
    if p_claim_token is null then
        return false;
    end if;

    update public.jarvis_agent_messages
       set status = 'delivered',
           delivered_at = now(),
           lease_expires_at = null,
           claim_token = null
     where message_id = p_message_id
       and recipient_id = p_agent_id
       and claimed_by = p_agent_id
       and claim_token = p_claim_token
       and status = 'claimed'
       and lease_expires_at > now();

    get diagnostics v_updated = row_count;
    return v_updated = 1;
end;
$$;

revoke all on function public.claim_jarvis_agent_message(text, integer)
    from public, anon, authenticated;
revoke all on function public.ack_jarvis_agent_message(uuid, text, uuid)
    from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_message(text, integer)
    to service_role;
grant execute on function public.ack_jarvis_agent_message(uuid, text, uuid)
    to service_role;
