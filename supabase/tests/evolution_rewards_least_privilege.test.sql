begin;
select plan(9);

select ok(
    (select relrowsecurity from pg_class where oid='public.evolution_rewards'::regclass),
    'evolution_rewards remains protected by RLS'
);
select is(
    (select count(*)::integer from pg_policies
      where schemaname='public' and tablename='evolution_rewards'),
    0,
    'no client-facing row policies are introduced'
);
select ok(
    not has_table_privilege('anon','public.evolution_rewards','SELECT')
    and not has_table_privilege('anon','public.evolution_rewards','INSERT')
    and not has_table_privilege('anon','public.evolution_rewards','UPDATE')
    and not has_table_privilege('anon','public.evolution_rewards','DELETE')
    and not has_table_privilege('anon','public.evolution_rewards','TRUNCATE')
    and not has_table_privilege('anon','public.evolution_rewards','REFERENCES')
    and not has_table_privilege('anon','public.evolution_rewards','TRIGGER'),
    'anon has no table privileges'
);
select ok(
    not has_table_privilege('authenticated','public.evolution_rewards','SELECT')
    and not has_table_privilege('authenticated','public.evolution_rewards','INSERT')
    and not has_table_privilege('authenticated','public.evolution_rewards','UPDATE')
    and not has_table_privilege('authenticated','public.evolution_rewards','DELETE')
    and not has_table_privilege('authenticated','public.evolution_rewards','TRUNCATE')
    and not has_table_privilege('authenticated','public.evolution_rewards','REFERENCES')
    and not has_table_privilege('authenticated','public.evolution_rewards','TRIGGER'),
    'authenticated has no table privileges'
);
select ok(
    not exists (
        select 1
          from pg_class c
          cross join lateral aclexplode(coalesce(c.relacl, acldefault('r',c.relowner))) a
         where c.oid='public.evolution_rewards'::regclass
           and a.grantee=0
    ),
    'PUBLIC has no table privileges'
);
select is(
    (select count(*)::integer
       from information_schema.column_privileges
      where table_schema='public'
        and table_name='evolution_rewards'
        and grantee in ('PUBLIC','anon','authenticated')),
    0,
    'PUBLIC and client roles have no column-level grants'
);
select ok(
    not has_sequence_privilege('anon','public.evolution_rewards_id_seq','USAGE')
    and not has_sequence_privilege('anon','public.evolution_rewards_id_seq','SELECT')
    and not has_sequence_privilege('anon','public.evolution_rewards_id_seq','UPDATE'),
    'anon cannot access the identity sequence'
);
select ok(
    not has_sequence_privilege('authenticated','public.evolution_rewards_id_seq','USAGE')
    and not has_sequence_privilege('authenticated','public.evolution_rewards_id_seq','SELECT')
    and not has_sequence_privilege('authenticated','public.evolution_rewards_id_seq','UPDATE'),
    'authenticated cannot access the identity sequence'
);
select ok(
    has_table_privilege('service_role','public.evolution_rewards','SELECT')
    and has_table_privilege('service_role','public.evolution_rewards','INSERT')
    and has_table_privilege('service_role','public.evolution_rewards','UPDATE')
    and has_table_privilege('service_role','public.evolution_rewards','DELETE')
    and has_sequence_privilege('service_role','public.evolution_rewards_id_seq','USAGE'),
    'service_role retains the privileges required by trusted backend writers'
);

select * from finish();
rollback;
