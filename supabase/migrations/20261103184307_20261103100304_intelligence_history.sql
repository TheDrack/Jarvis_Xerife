-- Durable, append-only history for normalized public intelligence events and entity observations.
-- The application computes SHA-256 content_hash values from canonical semantic payloads.
-- Event hashes exclude volatile observation/collection timestamps so repeated polling is idempotent.
-- Observation identity remains provider + entity type + entity ID + observed_at; distinct
-- same-time payload hashes may coexist so deterministic conflict resolution stays in IntelligenceCore.

create table if not exists public.intelligence_event_snapshots (
    id uuid primary key default gen_random_uuid(),
    source_id text not null check (length(source_id) between 1 and 100),
    event_id text not null check (length(event_id) between 1 and 160),
    domain text not null check (length(domain) between 1 and 80),
    category text not null check (length(category) between 1 and 100),
    published_at timestamptz,
    occurred_at timestamptz,
    observed_at timestamptz not null,
    ingested_at timestamptz not null default clock_timestamp(),
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    constraint intelligence_event_snapshots_idempotency unique (source_id, event_id, content_hash)
);
create index if not exists intelligence_event_snapshots_identity_history_idx
    on public.intelligence_event_snapshots (source_id, event_id, observed_at desc);
create index if not exists intelligence_event_snapshots_domain_time_idx
    on public.intelligence_event_snapshots (domain, category, observed_at desc);
create index if not exists intelligence_event_snapshots_ingested_idx
    on public.intelligence_event_snapshots (ingested_at desc);
alter table public.intelligence_event_snapshots enable row level security;
revoke all on table public.intelligence_event_snapshots from public, anon, authenticated, service_role;
grant select, insert on table public.intelligence_event_snapshots to service_role;
comment on table public.intelligence_event_snapshots is
    'Append-only, idempotent versions of normalized IntelligenceEvent records.';
comment on column public.intelligence_event_snapshots.observed_at is
    'Observation time carried by the normalized source record; not database arrival time.';
comment on column public.intelligence_event_snapshots.ingested_at is
    'Database-side ingestion timestamp, assigned independently of source observation time.';
comment on column public.intelligence_event_snapshots.content_hash is
    'SHA-256 of canonical semantic event content; excludes volatile observed/collected/ingested timestamps.';

create table if not exists public.intelligence_observation_snapshots (
    id uuid primary key default gen_random_uuid(),
    source_id text not null check (length(source_id) between 1 and 100),
    observation_id text not null check (length(observation_id) between 1 and 160),
    entity_type text not null check (length(entity_type) between 1 and 80),
    entity_id text not null check (length(entity_id) between 1 and 160),
    observed_at timestamptz not null,
    ingested_at timestamptz not null default clock_timestamp(),
    content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    constraint intelligence_observation_snapshots_idempotency
        unique (source_id, entity_type, entity_id, observed_at, content_hash)
);
create index if not exists intelligence_observation_snapshots_entity_history_idx
    on public.intelligence_observation_snapshots (source_id, entity_type, entity_id, observed_at desc);
create index if not exists intelligence_observation_snapshots_entity_time_idx
    on public.intelligence_observation_snapshots (entity_type, entity_id, observed_at desc);
create index if not exists intelligence_observation_snapshots_ingested_idx
    on public.intelligence_observation_snapshots (ingested_at desc);
alter table public.intelligence_observation_snapshots enable row level security;
revoke all on table public.intelligence_observation_snapshots from public, anon, authenticated, service_role;
grant select, insert on table public.intelligence_observation_snapshots to service_role;
comment on table public.intelligence_observation_snapshots is
    'Append-only, idempotent temporal snapshots of provider-specific entity observations.';
comment on column public.intelligence_observation_snapshots.observed_at is
    'Provider observation time; observations from different times remain distinct.';
comment on column public.intelligence_observation_snapshots.ingested_at is
    'Database-side ingestion timestamp, independent of provider observation time.';
comment on column public.intelligence_observation_snapshots.content_hash is
    'SHA-256 of canonical semantic observation content; excludes volatile evidence collection time.';