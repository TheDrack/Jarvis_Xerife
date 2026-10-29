-- Fix Postgres 42702 ambiguity in the expired/revoked refresh-token branch.
-- RETURNS TABLE exposes family_id as an OUT variable, so the UPDATE predicate
-- must qualify the table column to avoid resolving it as both a column and PL/pgSQL variable.
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
        update public.jarvis_mobile_device_sessions as s
           set revoked_at = coalesce(s.revoked_at, now())
         where s.family_id = v_session.family_id;
        return;
    end if;

    update public.jarvis_mobile_device_sessions as s
       set revoked_at = now(),
           last_used_at = now(),
           replaced_by_hash = p_replacement_hash
     where s.token_hash = p_token_hash;

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
