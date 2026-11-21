# Distributed Execution Architecture

**Status:** approved architectural direction; implementation roadmap  
**Decision date:** 2026-11-20  
**Decision:** hybrid and distributed execution across Android, PC, and Cloud  
**Scope:** runtime placement, worker identity, device capabilities, task continuity, and mobile execution

## 1. Decision

Jarvis is one logical system with multiple execution nodes. Android, PC, and Cloud are not separate Jarvis installations with independent task queues. They are execution environments connected to the same orchestration and task system.

The system must remain useful when any one node is unavailable. A task may move to another eligible node only when its declared requirements and security policy permit that move.

The OpenBot mobile-agent experience is a product reference, not a runtime dependency. Jarvis will use its own agent registry, task queue, identity model, tool authorization, memory, and user interfaces.

## 2. Existing components to reuse

The first implementation must extend these existing components rather than create parallel infrastructure:

- `app/multiagent/contracts.py`: `AgentProfile`, `TaskSpec`, `TaskAssignment`, and task status contracts.
- `app/multiagent/model_registry.py`: `ModelProfile`, `ModelRegistry`, `ModelRuntimeBindings`, and `ModelRuntime`.
- `app/application/services/agent_task_queue_service.py` and the existing PostgreSQL/Supabase queue: task persistence, claims, attempts, leases, recovery, and idempotency.
- `app/adapters/infrastructure/routers/agent_tasks.py`: authenticated worker heartbeat, claim, finish, and release endpoints.
- `app/adapters/infrastructure/agent_worker_credentials.py`: server-provisioned worker identity and capability grants.
- `app/multiagent/agent_worker_runtime.py` and `PriorityQueueMiniAgent`: supervised worker lifecycle and authenticated queue transport.
- `mobile/android`: native Android client, encrypted session storage, foreground bridge service, WebSocket, TTS, notifications, and environment observations.
- Existing Termux adapters and scripts: Android/Linux command and local-runtime integration, subject to explicit capability authorization.

Do not introduce a second task queue, a second model registry, or a second agent identity system.

## 3. Logical architecture

```text
User surfaces
  Android app / Mobile HUD / Desktop HUD / CLI / API / MCP
                         |
                  Jarvis API + Auth
                         |
              Intelligence / Orchestrator
                         |
             Existing shared task queue
             PostgreSQL / Supabase
                         |
              Placement and policy gate
                         |
       +-----------------+-----------------+
       |                 |                 |
  Android node        PC node          Cloud node
  Native APIs         Ubuntu/Windows   Linux workers
  Termux runtime      Host tools       Cloud tools
  Local models        Local models     Hosted models
       |                 |                 |
       +----------- audited results ------+
                         |
                Memory / Events / HUD
```

This is a logical topology, not a promise that all nodes are currently connected or production-ready.

## 4. Three Android operating modes

### 4.1 Mobile Controller

The Android app is the control surface for all authorized nodes:

- inspect agents, tasks, execution state, and results;
- submit and cancel tasks;
- approve gated actions;
- inspect audit events and device health;
- use voice, notifications, and the mobile HUD.

This builds on the existing native app and HUD WebView.

### 4.2 Mobile Worker

The phone executes only tasks compatible with its explicitly provisioned capabilities:

- Termux/Python worker for supported local workloads;
- native Android adapters for supported APIs (camera, microphone, location, notifications, files, and sensors);
- optional local inference when hardware and model constraints permit.

The Android app and Termux are separate Android applications and security principals. They must not be treated as one process or assumed to share credentials or filesystem access. Any bridge between them must be explicit, authenticated, user-enabled, and revocable.

The native app's existing foreground bridge remains the authenticated communication channel. It is not silently converted into an unrestricted shell.

### 4.3 Mobile Host

The phone may host a limited Jarvis runtime when its resources and Android execution restrictions permit. It is an optional node, not a required always-on server. Android battery management, Doze, process termination, thermal limits, storage, and network changes must be treated as normal availability conditions.

## 5. Node and worker identity

Keep these identities distinct:

- **User principal:** the authenticated account that owns a task or approves an action.
- **Node identity:** a server-assigned identity for a physical/logical execution environment, such as one Android installation, one PC runtime, or one cloud deployment.
- **Worker identity:** the immutable server-provisioned `agent_id` and `principal_id` used to claim and complete tasks.
- **Attempt identity:** the queue-generated attempt and lease that fences one execution attempt.
- **Model identity:** the selected model/provider profile; it is not the worker or node identity.

A node may host multiple workers. A logical agent may be redeployed on another node only through an explicit registration/provisioning flow; a self-asserted device name is not identity.

Worker credentials remain opaque, individually provisioned, hash-only at rest, expiring, rotatable, and revocable. User authentication and worker authentication remain separate credentials. Every claim, heartbeat, completion, and tool invocation must be bound to the authenticated worker and current attempt.

## 6. Capability and placement policy

A worker's self-reported environment, battery, network, model, and tool list are observations, not grants.

The server-side worker credential remains authoritative for the capabilities a worker may advertise to the scheduler. Host-backed tool execution must still pass the applicable authorization policy at invocation time.

The placement decision is evaluated in this order:

1. **Hard authorization:** worker credential valid, not revoked, and granted the required capabilities.
2. **Task constraints:** allowed/preferred environments, required tools/modalities, data locality, network requirements, and any user-selected node restriction.
3. **Safety:** task risk, approval requirements, executor isolation, and whether the target can enforce the requested controls.
4. **Availability:** fresh authenticated heartbeat, free concurrency slot, valid lease, and current node health.
5. **Optimization:** locality, estimated latency, cost, resource pressure, battery/thermal state, and provider/model availability.

A task must not be moved to a different environment merely because that environment is online. If no eligible worker satisfies the hard constraints, the task remains queued or transitions to an explicit blocked/approval state.

### Initial placement defaults

| Workload | Preferred environment | Fallback |
|---|---|---|
| General reasoning and orchestration | Cloud or available PC | Other eligible reasoning worker |
| Android-local actions and sensors | Android node | No remote fallback unless the task is redesigned |
| PC filesystem, desktop UI, or host process actions | PC node | No fallback to Android/Cloud without an explicit alternate implementation and authorization |
| Public web research and provider API calls | Cloud or PC | Any worker with the exact authorized connector |
| Large data processing / local datasets | PC or Cloud | Another node only if data access and transfer are authorized |
| Sensitive/local-only data | User-selected local node | None unless the user explicitly permits transfer |
| Privileged or destructive operations | Explicitly authorized host executor | Never downgrade to a less isolated executor |

## 7. Task contract evolution

Extend the existing task contract additively. Do not replace the queue or make existing task producers supply new fields.

The future optional execution policy should support:

- `allowed_environments`: hard allowlist such as `android`, `pc_linux`, `pc_windows`, or `cloud`;
- `preferred_environments`: ordered preferences, never authorization;
- `required_capabilities`: server-granted capability identifiers;
- `required_modalities`: model/runtime modalities;
- `locality`: `any`, `local_only`, or an explicit data-residency scope;
- `network_policy`: `offline_allowed`, `internet_required`, or a named approved network;
- `resource_hints`: CPU, memory, storage, battery, thermal, and accelerator requirements;
- `approval_policy`: whether a human approval is required before execution or before a specific side effect.

The API validates this policy at ingress. The scheduler filters workers using authoritative grants and fresh observations. The executor independently enforces authorization and sandbox policy. Unknown policy fields or unsupported constraints fail closed rather than being silently ignored.

## 8. Connectivity, leases, and recovery

- The existing shared PostgreSQL/Supabase task queue remains the source of truth.
- Workers claim tasks using the existing atomic claim/lease mechanism.
- A disconnected worker stops renewing its lease; the queue's existing expiry/recovery process may make the task eligible for another worker.
- A task is never considered completed because a client timed out. Completion is accepted only for the current task, worker, and attempt.
- Retries are at-least-once; task side effects must use stable idempotency keys or explicit reconciliation.
- Events and UI state are projections of queue state, not a second source of truth.
- The mobile notification/event queue remains for delivery of user-facing events; it is not repurposed as a second agent task queue.
- Offline Android-originated requests may be buffered only as idempotent intents with explicit expiry and later server acknowledgement. They do not execute privileged actions offline.

## 9. Security boundaries

- No arbitrary Python, shell, browser, desktop, or filesystem execution is granted by registering a worker.
- Android capabilities are individually scoped, user-enabled, and revocable. Accessibility, VPN, microphone, camera, location, and filesystem access each retain their platform permission model.
- Termux access must use an explicit bridge and a separate worker credential. Do not assume the Android app can execute Termux commands directly.
- PC host actions continue to require the host authorization policy and the hardened executor boundary. The mission execution route remains disabled until its separate sandbox requirements are met.
- Cloud workers receive only the secrets and data needed for their assigned task. Provider credentials are secret references injected at runtime, not plaintext database values.
- All state-changing operations record user, node, worker, task, attempt, tool, target/scope, timestamp, correlation ID, and outcome.
- Untrusted task content, web pages, files, and tool output are data, never authorization instructions.

## 10. Implementation roadmap

### D0 — Architecture and contracts

- Record this decision and map existing components.
- Define node registration, worker identity, capability grants, execution policy, and event/audit contracts.
- Preserve existing APIs with additive optional fields.

### D1 — Node registry and placement metadata

- Add server-owned node registration linked to existing worker credentials.
- Bind a worker to a node and immutable environment classification.
- Store last-seen and health observations without treating them as permissions.
- Add focused tests for impersonation, stale heartbeat, revoked credentials, and worker/node mismatch.

### D2 — Placement-aware shared queue

- Extend the existing task schema and queue claim function with optional execution constraints.
- Filter candidates by server grants, node binding, heartbeat freshness, risk and task constraints before optimization.
- Preserve current behavior for tasks with no execution policy.
- Add database integration tests for concurrency, lease expiry, idempotency, and no eligible worker.

### D3 — Android Mobile Worker

- Provision a dedicated Android/Termux worker identity with a narrow capability allowlist.
- Add authenticated heartbeat and worker lifecycle supervision.
- Start with non-privileged local workloads; add native Android adapters separately behind explicit permissions.
- Keep the native app as Controller even when the Termux worker is offline.
- Add Android/Termux integration and device smoke tests.

### D4 — PC and Cloud worker convergence

- Register Ubuntu/Windows and Cloud workers in the same node/worker model.
- Reuse the same queue and policy contracts.
- Add node-aware routing, health, resource telemetry, and safe failover.
- Keep host-only operations pinned to authorized host executors.

### D5 — Mobile-first operational HUD

- Show nodes, agents, models, tasks, attempts, capabilities, health, and active execution.
- Allow task submission, cancellation, approvals, and result inspection.
- Provide an explicit reason when a task cannot run on the current phone or must wait for another node.

## 11. Acceptance criteria

The architecture is not considered implemented until all of the following are demonstrated:

- Android, PC, and Cloud workers appear as distinct authenticated nodes.
- A worker cannot impersonate another worker or node.
- A worker cannot self-grant capabilities through heartbeat payloads.
- Tasks without placement constraints retain current behavior.
- Android-only tasks never run on PC or Cloud.
- PC-only host tasks never run on Android or Cloud.
- Local-only data does not leave its permitted node.
- A disconnected worker's expired lease can be recovered without accepting a stale completion.
- Retries do not duplicate protected side effects.
- A revoked worker cannot heartbeat, claim, finish, or invoke tools.
- The same task and attempt state is visible from Android, PC, and Cloud interfaces.
- Tests and coverage remain intact; no CI gate is disabled or weakened.
- Runtime claims are backed by dated device/host evidence, not merely by source files or passing unit tests.

## 12. Current implementation boundary (2026-11-20)

Present in the repository: shared worker queue, authenticated worker credentials, heartbeat/claim/finish/release APIs, model registry/runtime bindings, native Android session and foreground WebSocket bridge, mobile HUD, and Termux integration adapters.

Not yet established by this decision document: a server-owned node registry, placement-aware queue claims, a general Android/Termux task executor, cross-node failover in a live environment, or production verification of Android/PC/Cloud execution as one distributed system.

This document defines the target and sequencing. It does not claim those capabilities have already shipped.
