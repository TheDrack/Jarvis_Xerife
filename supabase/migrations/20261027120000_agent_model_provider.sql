-- Align the live agent registry with the runtime heartbeat contract.
-- Additive only: existing agents remain registered and retain their status.
alter table public.jarvis_agents
    add column if not exists model_provider text not null default 'unknown';

alter table public.jarvis_agents
    drop constraint if exists jarvis_agents_model_provider_nonempty;

alter table public.jarvis_agents
    add constraint jarvis_agents_model_provider_nonempty
    check (length(btrim(model_provider)) > 0);

create index if not exists jarvis_agents_live_heartbeat_idx
    on public.jarvis_agents (status, last_seen_at desc);
