-- Durable at-least-once message delivery for Jarvis multi-agent runtimes.
-- Apply to staging first; this migration is not applied automatically.
create table if not exists public.jarvis_agent_messages (
    message_id uuid primary key,
    task_id text not null,
    sender_id text not null,
    recipient_id text not null,
    kind text not null check (kind in ('request', 'ack', 'progress', 'result', 'error', 'cancel', 'proposal')),
    payload jsonb not null default '{}'::jsonb,
    correlation_id text,
    protocol_version text not null default '1.0',
    status text not null default 'pending' check (status in ('pending', 'claimed', 'delivered')),
    claimed_by text,
    claimed_at timestamptz,
    lease_expires_at timestamptz,
    delivery_attempts integer not null default 0 check (delivery_attempts >= 0),
    created_at timestamptz not null default now(),
    delivered_at timestamptz,
    constraint jarvis_message_claim_consistency check (
        (status = 'pending' and claimed_by is null and lease_expires_at is null and delivered_at is null)
        or (status = 'claimed' and claimed_by is not null and lease_expires_at is not null and delivered_at is null)
        or (status = 'delivered' and delivered_at is not null)
    )
);

create index if not exists jarvis_agent_messages_recipient_pending_idx
    on public.jarvis_agent_messages (recipient_id, created_at)
    where status = 'pending';

create index if not exists jarvis_agent_messages_expired_lease_idx
    on public.jarvis_agent_messages (recipient_id, lease_expires_at)
    where status = 'claimed';

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
    if p_lease_seconds < 1 or p_lease_seconds > 3600 then
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
           delivery_attempts = m.delivery_attempts + 1
     where m.message_id = v_message_id
    returning m.*;
end;
$$;

create or replace function public.ack_jarvis_agent_message(
    p_message_id uuid,
    p_agent_id text
)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_updated integer;
begin
    update public.jarvis_agent_messages
       set status = 'delivered',
           delivered_at = now(),
           lease_expires_at = null
     where message_id = p_message_id
       and recipient_id = p_agent_id
       and claimed_by = p_agent_id
       and status = 'claimed'
       and lease_expires_at > now();

    get diagnostics v_updated = row_count;
    return v_updated = 1;
end;
$$;

alter table public.jarvis_agent_messages enable row level security;
revoke all on public.jarvis_agent_messages from anon, authenticated;
revoke all on function public.claim_jarvis_agent_message(text, integer) from public, anon, authenticated;
revoke all on function public.ack_jarvis_agent_message(uuid, text) from public, anon, authenticated;
grant execute on function public.claim_jarvis_agent_message(text, integer) to service_role;
grant execute on function public.ack_jarvis_agent_message(uuid, text) to service_role;
grant select, insert, update on public.jarvis_agent_messages to service_role;
