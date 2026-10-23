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

The app.multiagent.contracts module defines runtime-neutral AgentProfile, TaskSpec, TaskAssignment, and lifecycle statuses. CostBenefitScheduler is the deterministic baseline: it filters by availability, capacity, required tools, and budget, then ranks by expected task value times measured success probability divided by estimated cost, coordination cost, and a configurable latency penalty.

The leader may assign work to itself or any eligible peer. The assigned role is task-scoped (task_type), not a permanent worker identity. The baseline score is a heuristic, not a calibrated probability; telemetry must improve it over time. Deadline and risk policies should be enforced as constraints by the orchestration layer before dispatch.

## Agent communication

app.multiagent.transport defines a versioned, JSON-safe envelope and a transport protocol. Concrete MCP, HTTP, or queue adapters must implement it. A message contains message/task identities, sender/recipient, kind, payload, correlation ID, and protocol version.

Message kinds are intentionally bounded: request, ack, progress, result, error, cancel, and proposal. Do not use free-form shared chat as the source of truth. Store substantial artifacts by reference and persist task state separately from messages.

## Supabase control-plane migration

supabase/migrations/202610230002_multi_agent_control_plane.sql adds agent profiles, tasks, attempts, and append-only events, with RLS enabled and direct anon/authenticated access revoked. The claim RPC is intended for trusted server-side callers only.

**The migration is versioned but must not be assumed applied to the live project.** Review the SQL, apply it to a staging project first, verify grants and concurrent claims, then apply it to the intended Supabase project using the approved deployment process. Never put a service_role key in agent prompts, desktop clients, or repository files.

## Failure and concurrency invariants

- Every task has a stable ID; every retry has a new attempt ID.
- Claims are leases, not permanent ownership. Expired work must be reconciled before reassignment.
- Use a monotonic fencing token to reject stale workers after reassignment.
- Use idempotency keys for external side effects; a durable queue does not guarantee exactly-once effects.
- One writer per shared file/branch; use isolated worktrees/branches for parallel engineering.
- A successful tool response is not proof of task completion; acceptance criteria and evidence must be verified.
- Destructive actions, closures, production deployments, credential changes, and permission expansion remain subject to explicit authorization.
- Recovery never overwrites a conflicting concurrent change or silently deletes newly created content.

## Implementation status

This branch adds the first runtime-neutral contracts, a deterministic cost-benefit assignment baseline, a transport interface, focused unit tests, and the initial Supabase schema. It does **not** yet provide a production MCP/HTTP queue adapter, an LLM-driven task decomposer, a running leader service, a heartbeat worker, lease renewal/reaping, or end-to-end deployment integration. Those should be implemented in small stages against the existing Harness APIs, not as a competing second runtime.
