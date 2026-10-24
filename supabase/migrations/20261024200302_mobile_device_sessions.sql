-- Revocable, rotating refresh sessions for native Jarvis Mobile.
-- The application server must use SUPABASE_SERVICE_ROLE_KEY for this table.
-- No browser/client role receives direct access.

create table if not exists public.jarvis_mobile_device_sessions (
    token_hash text primary key check (length(token_hash) = 64),
    family_id uuid not null,
    user_id text not null,
    username text not null,
    email text,
    full_name text,
    device_id text not null check (length(device_id) between 1 and 128),
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at timestamptz,
    replaced_by_hash text,
    check (replaced_by_hash is null or length(replaced_by_hash) = 64)
);

create index if not exists jarvis_mobile_sessions_family_idx
    on public.jarvis_mobile_device_sessions (family_id);
create index if not exists jarvis_mobile_sessions_device_idx
    on public.jarvis_mobile_device_sessions (user_id, device_id, expires_at);

alter table public.jarvis_mobile_device_sessions enable row level security;
revoke all on table public.jarvis_mobile_device_sessions from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_mobile_device_sessions to service_role;

-- Rotate atomically under a row lock. Reuse of a rotated or expired token
-- revokes the entire token family, which limits damage from refresh-token replay.
create or replace function public.rotate_jarvis_mobile_session(
    p_token_hash text,
    p_replacement_hash text,
    p_device_id text,
    p_expires_at timestamptz
)
returns table (
    user_id text,
    username text,
    email text,
    full_name text,
    family_id uuid
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_session public.jarvis_mobile_device_sessions%rowtype;
begin
    if length(p_token_hash) <> 64
       or length(p_replacement_hash) <> 64
       or length(p_device_id) not between 1 and 128
       or p_expires_at <= now()
       or p_expires_at > now() + interval '31 days' then
        return;
    end if;

    select s.* into v_session
      from public.jarvis_mobile_device_sessions as s
     where s.token_hash = p_token_hash
       and s.device_id = p_device_id
     for update;

    if not found then
        return;
    end if;

    if v_session.revoked_at is not null or v_session.expires_at <= now() then
        update public.jarvis_mobile_device_sessions
           set revoked_at = coalesce(revoked_at, now())
         where family_id = v_session.family_id;
        return;
    end if;

    update public.jarvis_mobile_device_sessions
       set revoked_at = now(),
           last_used_at = now(),
           replaced_by_hash = p_replacement_hash
     where token_hash = p_token_hash;

    insert into public.jarvis_mobile_device_sessions (
        token_hash, family_id, user_id, username, email, full_name,
        device_id, expires_at
    ) values (
        p_replacement_hash, v_session.family_id, v_session.user_id,
        v_session.username, v_session.email, v_session.full_name,
        v_session.device_id, p_expires_at
    );

    return query select
        v_session.user_id, v_session.username, v_session.email,
        v_session.full_name, v_session.family_id;
end;
$$;

revoke all on function public.rotate_jarvis_mobile_session(text, text, text, timestamptz)
    from public, anon, authenticated;
grant execute on function public.rotate_jarvis_mobile_session(text, text, text, timestamptz)
    to service_role;
