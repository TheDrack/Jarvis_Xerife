# ADR-001 — Universal Tool Registry boundaries and first increment

- **Status:** Accepted; registry, fail-closed dispatcher, and DAG toolchain implementation are present in PR #681. Production policy binding remains pending.
- **Date:** 2026-11-02
- **Related:** [Issue #680](https://github.com/TheDrack/Jarvis_Xerife/issues/680), [Global Intelligence #679](https://github.com/TheDrack/Jarvis_Xerife/issues/679)

## Context

The repository already has several overlapping but non-equivalent mechanisms:

- **Nexus DI** composes and resolves application components.
- **AdapterRegistry** inventories known adapters and capabilities, but is not a typed execution registry.
- **CapabilityAuthorizer** is a legacy authorization component; its current boolean confirmation inputs are not sufficient evidence for a future cross-runtime execution broker.
- **PipelineRunner** executes existing YAML steps through Nexus, but does not provide a versioned tool contract, typed input/output validation, or a universal execution lifecycle.
- **Connector adapters** such as Telegram and Google Drive already work behind concrete interfaces and must not be rewritten merely to introduce a common tool surface.

Creating a second dependency-injection container or moving provider SDKs into agents would duplicate responsibilities and increase coupling.

## Decision

### Responsibility boundaries

1. **Nexus remains the composition root.** It owns component construction, dependency injection, and lifecycle.
2. **ToolManifest describes one atomic tool version.** It declares a stable tool ID, semantic version, adapter ID, capabilities, object input/output schemas, dependencies, permissions, execution mode, trust/data classification, credential references, health policy, rate/cost limits, timeout, idempotency, side effects, and source terms.
3. **ToolRegistry is metadata-only.** It registers and discovers manifests. It does not instantiate adapters, probe health, resolve credentials, authorize callers, or execute tools.
4. **Tool Dispatcher / Execution Broker is a separate runtime boundary.** The implementation resolves an exact manifest version, validates input/output schemas, resolves adapters through Nexus, requires a dedicated host-provided ToolAuthorizationPolicy, applies timeouts/rate limits/circuit breakers/process-local idempotency, and emits secret-free audit events. It fails closed when trusted authorization is unavailable.
5. **Toolchains are typed, bounded DAG compositions.** They declare dependencies, explicit output bindings, budgets, cancellation, and retry limits. Existing YAML pipelines remain compatible; migration is incremental and requires explicit tool metadata plus regression evidence.

### Manifest and registry rules

- Tool IDs and adapter IDs are stable lowercase identifiers.
- Versions follow semantic versioning.
- A tool is resolved by the exact (tool_id, version) pair. The registry does not silently choose a latest version.
- Capability discovery uses exact identifiers, not substring matching.
- Duplicate (tool_id, version) registration is rejected unless replacement is explicitly requested by the caller.
- Credential fields contain references only (secret://, env://, or vault://), never credential values.
- Input and output schemas declare an object root using JSON Schema Draft 2020-12. The dispatcher validates request arguments and adapter outputs against these schemas when an output schema is declared.
- Health policy remains declarative; no remote health probe is implemented. The dispatcher enforces configured rate limits in-process. Registry presence alone is not health, authorization, availability, or production verification.
- Registered manifests are copied at ingress and egress so nested schema mutation by a caller cannot mutate registry state.

### Authorization requirements for execution

The dispatcher MUST NOT treat registry membership, CapabilityAuthorizer allowlist membership, a caller-provided username, or a boolean such as human_confirmed=true as sufficient authorization.

The execution boundary must receive a trusted principal from the host/runtime and a policy decision bound to at least:

- principal/session identity;
- tool ID and exact version;
- requested capability and scope/target;
- operation class and side effects;
- approval/grant identifier and expiry when human approval is required;
- correlation/request ID.

Read-only, active-bounded, and intervention tools must remain separate policy classes. Intervention requires explicit approval and post-action verification. External content and tool output remain untrusted data, not instructions.

## First implementation increment

The implementation increment represented by PR #681 adds:

- Pydantic v2 manifest and runtime request/result/authorization/audit contracts;
- a thread-safe in-memory ToolRegistry with exact version lookup, exact capability discovery, duplicate protection, deterministic listing, and defensive copies;
- a fail-closed ToolDispatcher that validates schemas, resolves adapters through Nexus, checks a host-provided policy decision bound to principal/session/tool/version/capability/scope/operation/expiry, applies bounded execution controls, and records secret-free audit metadata;
- typed DAG toolchains with explicit dependencies and output bindings, budgets, cancellation, and retries restricted to read-only retryable operations;
- explicit PipelineRunner compatibility for tool ID/version/capability, plus scoped Telegram, Drive, and passive local-network adapter operations;
- focused regression tests and full-suite CI validation.

The implementation does not register a production ToolAuthorizationPolicy. Without a host-backed principal/session resolver and approval verifier, real tool execution remains fail-closed. Durable shared idempotency/rate limits/circuit state/audit, remote health probes, forced cancellation of synchronous calls, and migration of all connectors remain pending.

## Consequences

### Positive

- Establishes one provider-neutral manifest shape without disturbing existing connectors.
- Prevents catalog metadata from being mistaken for executable permission.
- Makes tool identity/version deterministic for future routing and audit.
- Gives Global Intelligence (#679) a stable dependency boundary without embedding HTTP clients or provider SDKs in its agents.

### Trade-offs and deferred decisions

- The registry, idempotency cache, rate limiter, and circuit breaker are process-local; audit JSONL is local rather than a shared durable journal.
- Production authorization remains unavailable until a host-backed policy is registered; the safe behavior is to reject execution, not fall back to the legacy boolean authorizer.
- Remote health probes and forced cancellation of already-running synchronous adapter calls are not implemented.
- Existing connector APIs remain available; each migration requires compatibility tests and explicit runtime evidence.

## Validation

PR #681 CI on code HEAD `ca21d51098239d211ec1843ba06eea15d1ca3603` passed the full suite in both environments: Linux/Python 3.11.17, run [41531685329](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/41531685329), 2043 passed, 12 skipped, 9 warnings, 60% coverage; Windows/Python 3.12.10, run [41531685413](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/41531685413), 2043 passed, 12 skipped, 49 warnings, 60% coverage. The suite includes the principal-scoped idempotency regression test. CI is read-only and does not touch production connectors, credentials, devices, or external services. A production policy and runtime integration remain unverified.
