-- evolution_rewards is an internal reward ledger, not a client-facing API.
-- Keep the existing RLS posture and service_role access; remove public/client
-- table, column, and identity-sequence grants.
do $$
declare
    v_columns text;
    v_sequence regclass;
begin
    if to_regclass('public.evolution_rewards') is null then
        raise exception 'public.evolution_rewards must exist before privilege hardening';
    end if;

    select string_agg(format('%I', a.attname), ', ' order by a.attnum)
      into v_columns
      from pg_attribute a
     where a.attrelid = 'public.evolution_rewards'::regclass
       and a.attnum > 0
       and not a.attisdropped;

    revoke all privileges on table public.evolution_rewards
        from public, anon, authenticated;

    execute format(
        'revoke select (%s) on table public.evolution_rewards from public, anon, authenticated',
        v_columns
    );
    execute format(
        'revoke insert (%s) on table public.evolution_rewards from public, anon, authenticated',
        v_columns
    );
    execute format(
        'revoke update (%s) on table public.evolution_rewards from public, anon, authenticated',
        v_columns
    );
    execute format(
        'revoke references (%s) on table public.evolution_rewards from public, anon, authenticated',
        v_columns
    );

    v_sequence := pg_get_serial_sequence('public.evolution_rewards', 'id')::regclass;
    if v_sequence is not null then
        execute format(
            'revoke all privileges on sequence %s from public, anon, authenticated',
            v_sequence
        );
    end if;
end;
$$;
