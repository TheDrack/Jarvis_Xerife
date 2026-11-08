# Agent Worker Identity and Capability Grants

**Status:** first implementation slice; production rollout not verified  
**Roadmap:** C0 — Trusted Worker Identity & Capability Attestation  
**Migration:** `20261107183000_agent_worker_credentials.sql`

## Identity model

Task-queue worker requests carry two independent credentials:

1. `Authorization: Bearer <user-jwt>` authenticates the API caller through the existing user authentication path. The user principal remains available for user-scoped behavior such as the proposal-only `task_blocked` signal.
2. `X-Jarvis-Worker-Token: <opaque-token>` authenticates one registered worker. The server resolves the token hash to an immutable `agent_id`, `principal_id`, and server-provisioned capability list.

The worker's `agent_id` in the request body must exactly match the credential's registered `agent_id`. A mismatch is rejected with HTTP 403. A missing, expired, unknown, or revoked worker credential is rejected with HTTP 401. If the credential registry cannot be reached, the API fails closed with HTTP 503.

Provisioning first marks the agent offline and replaces its persisted capability list with the new server grant. Revocation marks it offline and clears its capabilities. This prevents stale capabilities from an older, self-reported heartbeat remaining schedulable while a replacement worker has not yet authenticated.

The worker token is generated from 48 bytes of cryptographic randomness with the `jarvisw_` prefix. Only its SHA-256 hash is stored. Tokens are displayed once by the provisioning CLI, expire within 90 days, and are rotated atomically: issuing a replacement revokes previous active credentials for that agent. Revocation is available per agent.

## Capability boundary

The heartbeat's client-supplied `available_tools` is ignored. The API writes the capability grant stored in the credential record. The initial allowlist contains only `text_reasoning`; repository, GitHub, shell, browser, Supabase, Render, and production capabilities cannot be provisioned by this implementation.

This is a server-controlled capability grant, not proof of a runtime executor's health. The next increment must bind grants to an attested executor registry and the host-backed `ToolAuthorizationPolicy`. Do not expand the allowlist merely because an agent requests a capability.

## Provisioning

The provisioning command uses a trusted PostgreSQL connection from `JARVIS_TASK_QUEUE_DATABASE_URL` or `DATABASE_URL`. It does not call a public provisioning endpoint.

Issue or rotate a text-only worker credential:

```powershell
python scripts/manage_agent_worker_credentials.py issue --agent-id mini-freellmapi-1
```

The command prints the raw token once. Store it in the matching worker's secret environment as `JARVIS_TASK_QUEUE_WORKER_TOKEN`; do not commit it, put it in a prompt, or copy it into logs. The worker also needs the existing API caller identity: `JARVIS_TASK_QUEUE_API_TOKEN` (user JWT) or `JARVIS_TASK_QUEUE_USERNAME` plus `JARVIS_TASK_QUEUE_PASSWORD`, and `JARVIS_TASK_QUEUE_API_URL`. Store the token in the exact per-agent variable printed by the CLI (for example `JARVIS_TASK_QUEUE_WORKER_TOKEN_MINI_FREELLMAPI_1`). The global `JARVIS_TASK_QUEUE_WORKER_TOKEN` is accepted only when the runtime has one slot. Multiple slots require one distinct token per generated `agent_id`; a shared token is rejected.

Revoke every active credential for an agent:

```powershell
python scripts/manage_agent_worker_credentials.py revoke --agent-id mini-freellmapi-1
```

The provisioning script requires a database role allowed to write the service-only credential table. It does not apply migrations. The migration must be reviewed and applied through the repository's normal GitHub–Supabase integration after merge; do not run `db push` or manual DDL as part of provisioning.

## Runtime selection and migration

`PriorityQueueMiniAgent` sends the user JWT and worker token in separate headers. `agent_worker_runtime` prefers this authenticated HTTP path when the API URL, worker token, and user caller identity are all configured. If a worker token is configured incompletely, startup fails closed rather than silently falling back to the service-role path.

The direct `SupabaseTaskQueueMiniAgent` service-role path remains as an explicit legacy fallback for installations not yet provisioned. The runtime logs a warning when that path is selected. It bypasses this per-agent HTTP identity boundary and is not considered trusted-worker authentication. Do not claim C0 identity is complete until production workers are migrated and this fallback is removed or separately constrained.

## Acceptance evidence

Tests cover:

- one-time token issuance and hash-only persistence;
- server-side agent registration;
- authentication resolving the registered identity and capabilities;
- expiry and revocation rejection;
- rotation invalidating the previous token;
- unsupported capability rejection;
- heartbeat ignoring client-supplied capabilities;
- heartbeat and claim rejecting agent impersonation;
- missing and invalid worker-token rejection;
- runtime preference for the bound HTTP path and fail-closed handling of incomplete configuration.

## Remaining C0 work

- Migrate the Supabase-native worker away from direct service-role task access.
- Keep the task owner (derived from the persisted task), worker credential principal, and active attempt executor as separate identities. The host policy now derives the effective owner from the task record and records the worker executor independently; it does not compare a `worker:*` principal directly with the task owner.
- Add host/runtime executor attestation; the current `text_reasoning` grant is provisioned, not dynamically attested.
- Add an authenticated approval-intent creation/confirmation API that derives the owner and approver session from verified auth context; the durable store primitive exists in PR #780 but is not deployed or wired.
- Implement and register a production host-backed `ToolAuthorizationPolicy` with real principal/session/task/attempt resolvers, atomic approval consumption, and Nexus composition.
- Verify two independently provisioned workers, cross-agent rejection, revocation, owner isolation, and complete queue execution in an isolated Supabase integration environment.
- Provision production credentials only after the migration is deployed and a controlled rollout is explicitly authorized.
