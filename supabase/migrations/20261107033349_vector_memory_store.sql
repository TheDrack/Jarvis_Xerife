-- Durable, user-partitioned semantic memory for the VectorMemoryAdapter.
create table if not exists public.jarvis_vector_memories (
    id uuid primary key default gen_random_uuid(),
    user_id text,
    scope_key text not null,
    event_text text not null,
    embedding jsonb not null,
    metadata jsonb not null default '{}'::jsonb,
    vector_dim integer not null,
    created_at timestamptz not null default now(),
    constraint jarvis_vector_memories_scope_consistency_check
        check (
            (user_id is null and scope_key = 'system')
            or (user_id is not null and scope_key = 'user:' || user_id)
        ),
    constraint jarvis_vector_memories_embedding_shape_check
        check (
            jsonb_typeof(embedding) = 'array'
            and jsonb_array_length(embedding) = vector_dim
            and vector_dim > 0
        ),
    constraint jarvis_vector_memories_metadata_shape_check
        check (
            jsonb_typeof(metadata) = 'object'
            and not (metadata ? 'user_id')
        )
);

create index if not exists jarvis_vector_memories_scope_created_idx
    on public.jarvis_vector_memories (scope_key, created_at desc);

alter table public.jarvis_vector_memories enable row level security;

revoke all on table public.jarvis_vector_memories
    from public, anon, authenticated, service_role;

grant select, insert, delete on table public.jarvis_vector_memories
    to service_role;

comment on table public.jarvis_vector_memories is
    'Durable user-partitioned semantic memory; service-role access only, with user scope enforced by the trusted adapter.';
