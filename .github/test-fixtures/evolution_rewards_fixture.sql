create table public.evolution_rewards (
    id serial primary key,
    action_type varchar not null,
    reward_value double precision not null,
    context_data json,
    meta_data json,
    created_at timestamp without time zone not null default now()
);
alter table public.evolution_rewards enable row level security;
grant all privileges on table public.evolution_rewards to anon, authenticated, service_role;
grant all privileges on sequence public.evolution_rewards_id_seq to anon, authenticated, service_role;
grant select (id, action_type, reward_value, context_data, meta_data, created_at)
    on table public.evolution_rewards to anon, authenticated;
grant insert (id, action_type, reward_value, context_data, meta_data, created_at)
    on table public.evolution_rewards to anon, authenticated;
grant update (id, action_type, reward_value, context_data, meta_data, created_at)
    on table public.evolution_rewards to anon, authenticated;
grant references (id, action_type, reward_value, context_data, meta_data, created_at)
    on table public.evolution_rewards to anon, authenticated;
