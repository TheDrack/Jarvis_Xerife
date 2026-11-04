-- Distributed lease, fenced RPCs and append-only collection telemetry.
-- This migration is intentionally separate from the history schema migration.
create table if not exists public.jarvis_intelligence_worker_lease (
    singleton_id smallint primary key default 1 check (singleton_id = 1),
    worker_id text,
    lease_expires_at timestamptz,
    updated_at timestamptz not null default clock_timestamp()
);
insert into public.jarvis_intelligence_worker_lease (singleton_id)
values (1) on conflict (singleton_id) do nothing;

alter table public.jarvis_intelligence_worker_lease enable row level security;
revoke all on table public.jarvis_intelligence_worker_lease from public, anon, authenticated, service_role;

create table if not exists public.jarvis_intelligence_worker_runs (
    id bigint generated always as identity primary key,
    worker_id text not null,
    status text not null check (status in ('completed', 'failed')),
    started_at timestamptz not null,
    finished_at timestamptz not null,
    duration_ms integer not null check (duration_ms >= 0),
    event_count integer not null default 0 check (event_count >= 0),
    observation_count integer not null default 0 check (observation_count >= 0),
    error_code text,
    history_metrics jsonb not null default '{}'::jsonb check (jsonb_typeof(history_metrics) = 'object'),
    retention_observation_days integer not null check (retention_observation_days between 1 and 3650),
    created_at timestamptz not null default clock_timestamp()
);
create index if not exists jarvis_intelligence_worker_runs_created_idx
    on public.jarvis_intelligence_worker_runs (created_at desc);
alter table public.jarvis_intelligence_worker_runs enable row level security;
revoke all on table public.jarvis_intelligence_worker_runs from public, anon, authenticated, service_role;
grant select, insert on table public.jarvis_intelligence_worker_runs to service_role;
grant usage, select on sequence public.jarvis_intelligence_worker_runs_id_seq to service_role;

create or replace function public.claim_jarvis_intelligence_worker_lease(
    p_worker_id text, p_lease_seconds integer
) returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare v_claimed boolean := false;
begin
    if p_worker_id is null or length(trim(p_worker_id)) not between 1 and 160
       or p_lease_seconds is null or p_lease_seconds not between 30 and 3600 then
        raise exception 'invalid worker lease parameters';
    end if;
    insert into public.jarvis_intelligence_worker_lease
        (singleton_id, worker_id, lease_expires_at, updated_at)
    values (1, p_worker_id, clock_timestamp() + make_interval(secs => p_lease_seconds), clock_timestamp())
    on conflict (singleton_id) do update
        set worker_id = excluded.worker_id,
            lease_expires_at = excluded.lease_expires_at,
            updated_at = clock_timestamp()
        where public.jarvis_intelligence_worker_lease.lease_expires_at is null
           or public.jarvis_intelligence_worker_lease.lease_expires_at <= clock_timestamp()
           or public.jarvis_intelligence_worker_lease.worker_id = p_worker_id
    returning true into v_claimed;
    return coalesce(v_claimed, false);
end;
$$;

create or replace function public.renew_jarvis_intelligence_worker_lease(
    p_worker_id text, p_lease_seconds integer
) returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    if p_worker_id is null or p_lease_seconds is null
       or p_lease_seconds not between 30 and 3600 then
        return false;
    end if;
    update public.jarvis_intelligence_worker_lease
       set lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
           updated_at = clock_timestamp()
     where singleton_id = 1 and worker_id = p_worker_id
       and lease_expires_at > clock_timestamp();
    return found;
end;
$$;

create or replace function public.release_jarvis_intelligence_worker_lease(
    p_worker_id text
) returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    update public.jarvis_intelligence_worker_lease
       set worker_id = null, lease_expires_at = null, updated_at = clock_timestamp()
     where singleton_id = 1 and worker_id = p_worker_id;
    return found;
end;
$$;

create or replace function public.record_jarvis_intelligence_worker_run(
    p_worker_id text, p_payload jsonb
) returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare v_started timestamptz; v_finished timestamptz; v_status text;
begin
    if p_payload is null or jsonb_typeof(p_payload) <> 'object' then return false; end if;
    if not exists (
        select 1 from public.jarvis_intelligence_worker_lease
         where singleton_id = 1 and worker_id = p_worker_id
           and lease_expires_at > clock_timestamp()
    ) then return false; end if;
    v_started := to_timestamp((p_payload->>'started_at_epoch')::double precision);
    v_finished := to_timestamp((p_payload->>'finished_at_epoch')::double precision);
    v_status := p_payload->>'status';
    if v_status not in ('completed', 'failed') or v_started is null or v_finished is null then
        return false;
    end if;
    insert into public.jarvis_intelligence_worker_runs (
        worker_id, status, started_at, finished_at, duration_ms,
        event_count, observation_count, error_code, history_metrics,
        retention_observation_days
    ) values (
        p_worker_id, v_status, v_started, v_finished,
        greatest(0, coalesce((p_payload->>'duration_ms')::integer, 0)),
        greatest(0, coalesce((p_payload->>'event_count')::integer, 0)),
        greatest(0, coalesce((p_payload->>'observation_count')::integer, 0)),
        nullif(p_payload->>'error_code', ''),
        coalesce(p_payload->'history_metrics', '{}'::jsonb),
        greatest(1, least(3650, coalesce((p_payload->>'retention_observation_days')::integer, 90)))
    );
    return true;
exception when others then
    return false;
end;
$$;

create or replace function public.get_jarvis_intelligence_history_metrics()
returns jsonb
language sql
security definer
set search_path = pg_catalog, public
as $$
    select jsonb_build_object(
        -- pg_stat estimates avoid a full COUNT(*) scan on every worker cycle.
        'event_count', coalesce((select n_live_tup::bigint from pg_stat_user_tables
            where schemaname = 'public' and relname = 'intelligence_event_snapshots'), 0),
        'observation_count', coalesce((select n_live_tup::bigint from pg_stat_user_tables
            where schemaname = 'public' and relname = 'intelligence_observation_snapshots'), 0),
        'row_counts_are_estimates', true,
        'oldest_event_ingested_at', (select ingested_at from public.intelligence_event_snapshots order by ingested_at asc limit 1),
        'oldest_observation_ingested_at', (select ingested_at from public.intelligence_observation_snapshots order by ingested_at asc limit 1),
        'event_table_bytes', pg_total_relation_size('public.intelligence_event_snapshots'::regclass),
        'observation_table_bytes', pg_total_relation_size('public.intelligence_observation_snapshots'::regclass),
        'measured_at', clock_timestamp()
    );
$$;

revoke all on function public.claim_jarvis_intelligence_worker_lease(text, integer) from public, anon, authenticated;
revoke all on function public.renew_jarvis_intelligence_worker_lease(text, integer) from public, anon, authenticated;
revoke all on function public.release_jarvis_intelligence_worker_lease(text) from public, anon, authenticated;
revoke all on function public.record_jarvis_intelligence_worker_run(text, jsonb) from public, anon, authenticated;
revoke all on function public.get_jarvis_intelligence_history_metrics() from public, anon, authenticated;
grant execute on function public.claim_jarvis_intelligence_worker_lease(text, integer) to service_role;
grant execute on function public.renew_jarvis_intelligence_worker_lease(text, integer) to service_role;
grant execute on function public.release_jarvis_intelligence_worker_lease(text) to service_role;
grant execute on function public.record_jarvis_intelligence_worker_run(text, jsonb) to service_role;
grant execute on function public.get_jarvis_intelligence_history_metrics() to service_role;
