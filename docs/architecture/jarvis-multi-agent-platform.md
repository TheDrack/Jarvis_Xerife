# Jarvis Multi-Agent Platform — Implementation Plan

## Architectural invariant

Every participating agent runs a compatible version of the same Jarvis Harness and receives the same standard tool/skill catalog. Roles such as research, implementation, review, and infrastructure are **temporary task assignments chosen by the leader**, not separate agent products or permanently restricted worker classes.

Shared tools do not imply shared context or blanket permission. Each runtime retains its own model/context and must authorize every tool invocation under its local policy.

## Logical components

- **Harness Core:** lifecycle, tool execution, evidence, validation, and recovery hooks.
- **Tool/Skill Catalog:** common versioned capabilities available to all compatible runtimes.
- **Connectors:** adapters for MCP, authenticated HTTP, durable task queues, and remote execution.
- **Task Protocol:** versioned task, assignment, message, status, and result contracts.
- **Leader/Scheduler:** decomposes goals, assigns temporary roles, selects agents by capability, success history, cost, latency, capacity, and risk, and consolidates verified results.
- **Shared control plane:** durable tasks, leases, attempts, costs, agent heartbeats, artifacts, and append-only events.
- **Security and recovery:** per-tool authorization, fencing tokens, checkpoints, conflict detection, and explicit approval for destructive actions.

## Connectivity and shared state

Use the existing topology rather than creating a second network:

- Tailscale connects authorized nodes.
- Aperture gates access to configured models and MCP tools.
- Supabase stores durable shared control-plane state.
- Jarvis connectors bridge each Harness to the communication/task protocol.

The existing preferred operational route remains RDC → Aperture → Tailscale → Jarvis. The desktop route is for operational access; task coordination should use authenticated service endpoints/queue connectors rather than treating remote desktop as the message bus.

## Dynamic assignment policy

The `app.multiagent.contracts` module defines runtime-neutral `AgentProfile`, `TaskSpec`, `TaskAssignment`, and lifecycle statuses. `CostBenefitScheduler` is the deterministic baseline: it filters by availability, capacity, required tools, and budget, then ranks by expected task value times measured success probability divided by estimated cost, coordination cost, and a configurable latency penalty.

The leader may assign work to itself or any eligible peer. The assigned role is task-scoped (`task_type`), not a permanent worker identity. The baseline score is a heuristic, not a calibrated probability; telemetry must improve it over time. Deadline and risk policies should be enforced as constraints by the orchestration layer before dispatch.

## Agent communication and worker

`app.multiagent.transport` defines a versioned, JSON-safe envelope and connector protocol. `SupabaseQueueConnector` is the first durable connector: it stores messages in Supabase, claims them through a transactional RPC using `FOR UPDATE SKIP LOCKED`, and leases claims to a recipient agent.

`AgentWorker.process_once()` receives one message, invokes an injected handler, publishes a correlated `result` for successful `request` messages, then acknowledges the original message. If the handler or result publication raises, it deliberately leaves the message unacknowledged so it can be redelivered after lease expiry. A failed acknowledgement raises an error; the worker does not silently report success.

Delivery is **at-least-once**, not exactly-once. A crash after publishing a result but before acknowledging the request may cause a duplicate result, so consumers should deduplicate by correlation ID and keep handlers/external side effects idempotent. This worker is a processing primitive, not yet a managed long-running service: process supervision, heartbeat, graceful shutdown, and lease renewal are still required.

Message kinds are bounded: `request`, `ack`, `progress`, `result`, `error`, `cancel`, and `proposal`. A message is a request, not an authorization grant. Do not use free-form shared chat as the source of truth; store substantial artifacts by reference and persist task state separately from messages.

## Supabase migrations

- `202610230002_multi_agent_control_plane.sql`: agent profiles, tasks, attempts, events, RLS, and task claim/completion RPCs.
- `202610230003_multi_agent_message_queue.sql`: durable message table, leased claim RPC, acknowledgement RPC, and least-privilege grants.

**Neither migration should be assumed applied to the live project.** Review the SQL and apply it to a staging project first; verify grants, concurrent claims, lease expiry/redelivery, acknowledgement ownership, and behavior under concurrent consumers. Only then apply to the intended Supabase project through the approved deployment process. Never put a `service_role` key in agent prompts, desktop clients, or repository files. The connector requires a trusted server-side client.

## Failure and concurrency invariants

- Every task has a stable ID; every retry has a new attempt ID.
- Message claims are leases, not permanent ownership. Expired messages may be delivered again.
- Task fencing tokens reject stale workers after reassignment; queue message leases do not replace task-level fencing.
- Use idempotency keys for external side effects; a durable queue does not guarantee exactly-once effects.
- One writer per shared file/branch; use isolated worktrees/branches for parallel engineering.
- A successful tool response is not proof of task completion; acceptance criteria and evidence must be verified.
- Destructive actions, closures, production deployments, credential changes, and permission expansion remain subject to explicit authorization.
- Recovery never overwrites a conflicting concurrent change or silently deletes newly created content.

## Implementation status

Implemented: shared contracts, deterministic cost-benefit scheduling, thin leader dispatch, the transport protocol, the Supabase task/control-plane adapter, a durable Supabase message queue with leased claims and acknowledgements, a one-message worker primitive, focused unit tests, and initial schema migrations.

Still required before production: run focused tests against the exact branch, validate both migrations against a staging Supabase/Postgres instance, test real concurrent claims and lease expiry, add agent heartbeat/health reconciliation and lease renewal, integrate task decomposition with the existing Harness, and run an end-to-end test with two real Harness runtimes. No production migration or deployment is performed by this change.
