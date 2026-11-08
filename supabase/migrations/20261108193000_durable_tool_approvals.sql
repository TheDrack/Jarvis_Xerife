-- Durable, single-use approvals for exact toolbox requests.
-- Only the trusted server role may read or mutate approval records.

create table if not exists public.jarvis_tool_approvals (
    approval_id text primary key,
    principal_id text not null
        check (length(btrim(principal_id)) between 1 and 256),
    task_id text,
    tool_id text not null
        check (length(btrim(tool_id)) between 3 and 128),
    tool_version text not null
        check (tool_version ~ '^[0-9]+[.][0-9]+[.][0-9]+$'),
    capability text not null
        check (length(btrim(capability)) between 1 and 128),
    scope text not null
        check (length(btrim(scope)) between 1 and 256),
    operation text not null
        check (length(btrim(operation)) between 1 and 128),
    arguments_digest text not null
        check (arguments_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key text,
    status text not null default 'pending'
        check (status in ('pending', 'approved', 'revoked', 'consumed')),
    approver_session_id text,
    created_at timestamptz not null default now(),
    approved_at timestamptz,
    expires_at timestamptz not null,
    revoked_at timestamptz,
    consumed_at timestamptz,
    consumed_by text,
    check (expires_at > created_at),
    check (
        (status = 'pending' and approved_at is null and approver_session_id is null
            and consumed_at is null and revoked_at is null)
        or (status = 'approved' and approved_at is not null
            and approver_session_id is not null and consumed_at is null and revoked_at is null)
        or (status = 'revoked' and revoked_at is not null and consumed_at is null)
        or (status = 'consumed' and approved_at is not null
            and approver_session_id is not null and consumed_at is not null
            and consumed_by is not null and revoked_at is null)
    )
);

create index if not exists jarvis_tool_approvals_owner_status_expiry_idx
    on public.jarvis_tool_approvals (principal_id, status, expires_at);

create index if not exists jarvis_tool_approvals_task_idx
    on public.jarvis_tool_approvals (task_id, status)
    where task_id is not null;

alter table public.jarvis_tool_approvals enable row level security;
revoke all on table public.jarvis_tool_approvals from public, anon, authenticated;
grant select, insert, update, delete on table public.jarvis_tool_approvals to service_role;

comment on table public.jarvis_tool_approvals is
    'Server-only exact-intent approvals; consumption is atomic and single-use.';
comment on column public.jarvis_tool_approvals.approver_session_id is
    'Authenticated session that approved the request; distinct from a later worker execution session.';
