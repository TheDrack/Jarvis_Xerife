begin;
select plan(5);

select is(
    (select prorettype::regtype::text from pg_proc
      where oid='public.rls_auto_enable()'::regprocedure),
    'event_trigger',
    'rls_auto_enable remains an event-trigger function'
);
select ok(
    exists (
        select 1 from pg_event_trigger e
         where e.evtname='ensure_rls'
           and e.evtfoid='public.rls_auto_enable()'::regprocedure
           and e.evtenabled='O'
    ),
    'ensure_rls remains attached and enabled'
);
select ok(
    not exists (
        select 1
          from pg_proc p
          cross join lateral aclexplode(coalesce(p.proacl, acldefault('f',p.proowner))) a
         where p.oid='public.rls_auto_enable()'::regprocedure
           and a.grantee=0
           and a.privilege_type='EXECUTE'
    ),
    'PUBLIC has no direct EXECUTE privilege'
);
select ok(
    not has_function_privilege('anon','public.rls_auto_enable()','EXECUTE')
    and not has_function_privilege('authenticated','public.rls_auto_enable()','EXECUTE')
    and not has_function_privilege('service_role','public.rls_auto_enable()','EXECUTE')
    and has_function_privilege('postgres','public.rls_auto_enable()','EXECUTE'),
    'only the function owner retains direct EXECUTE'
);

create table public.rls_auto_enable_probe (
    id bigint generated always as identity primary key
);
select ok(
    (select relrowsecurity from pg_class where oid='public.rls_auto_enable_probe'::regclass),
    'event trigger still enables RLS on a newly created public table after ACL revocation'
);

select * from finish();
rollback;
