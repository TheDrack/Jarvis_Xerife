-- Durable vector-memory table isolation and least-privilege contract.
begin;
select plan(13);

select ok(
    to_regclass('public.jarvis_vector_memories') is not null,
    'durable vector memory table exists'
);
select ok(
    (select relrowsecurity from pg_class where oid = 'public.jarvis_vector_memories'::regclass),
    'row-level security is enabled'
);
select is(
    (select count(*)::integer from pg_policies
      where schemaname = 'public' and tablename = 'jarvis_vector_memories'),
    0,
    'no client-facing policies are installed'
);
select ok(
    has_table_privilege('service_role', 'public.jarvis_vector_memories', 'SELECT'),
    'service role can read scoped memory'
);
select ok(
    has_table_privilege('service_role', 'public.jarvis_vector_memories', 'INSERT'),
    'service role can append memory'
);
select ok(
    has_table_privilege('service_role', 'public.jarvis_vector_memories', 'DELETE'),
    'service role can delete a scoped partition'
);
select ok(
    not has_table_privilege('service_role', 'public.jarvis_vector_memories', 'UPDATE'),
    'service role cannot mutate an existing memory row'
);
select ok(
    not has_table_privilege('anon', 'public.jarvis_vector_memories', 'SELECT')
    and not has_table_privilege('anon', 'public.jarvis_vector_memories', 'INSERT'),
    'anon cannot read or write vector memory'
);
select ok(
    not has_table_privilege('authenticated', 'public.jarvis_vector_memories', 'SELECT')
    and not has_table_privilege('authenticated', 'public.jarvis_vector_memories', 'INSERT'),
    'authenticated clients cannot access vector memory directly'
);
select ok(
    to_regclass('public.jarvis_vector_memories_scope_created_idx') is not null,
    'user scope and recency lookup is indexed'
);
select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.jarvis_vector_memories'::regclass
          and conname = 'jarvis_vector_memories_scope_consistency_check'
    ),
    'scope key must match the authoritative user id'
);
select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.jarvis_vector_memories'::regclass
          and conname = 'jarvis_vector_memories_embedding_shape_check'
    ),
    'embedding must be a non-empty array matching vector dimension'
);
select ok(
    exists (
        select 1 from pg_constraint
        where conrelid = 'public.jarvis_vector_memories'::regclass
          and conname = 'jarvis_vector_memories_metadata_shape_check'
    ),
    'metadata cannot override the trusted user id'
);

select * from finish();
rollback;
