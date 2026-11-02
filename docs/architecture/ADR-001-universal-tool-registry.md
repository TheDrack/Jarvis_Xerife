# ADR-001 — Universal Tool Registry boundaries and first increment

- **Status:** Accepted for the metadata/registry foundation; dispatcher decision remains open.
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
4. **Tool Dispatcher / Execution Broker is a separate future boundary.** It will resolve an exact manifest version, validate request arguments, resolve the adapter through Nexus, evaluate policy, execute within bounded resource limits, validate the result, and emit audit/evidence events.
5. **Toolchains are declarative compositions.** Existing YAML pipelines remain unchanged until a later compatibility increment proves equivalent order, context propagation, failure semantics, and rollback behavior.

### Manifest and registry rules

- Tool IDs and adapter IDs are stable lowercase identifiers.
- Versions follow semantic versioning.
- A tool is resolved by the exact (tool_id, version) pair. The registry does not silently choose a latest version.
- Capability discovery uses exact identifiers, not substring matching.
- Duplicate (tool_id, version) registration is rejected unless replacement is explicitly requested by the caller.
- Credential fields contain references only (secret://, env://, or vault://), never credential values.
- Input and output schemas declare an object root using JSON Schema Draft 2020-12. This increment checks the manifest envelope; it does not claim full JSON Schema instance validation.
- Health policy and rate/cost limits are declarations only. Registry presence is not health, authorization, availability, or production verification.
- Registered manifests are copied at ingress and egress so nested schema mutation by a caller cannot mutate registry state.

### Authorization requirements before execution exists

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

This ADR's first code increment adds:

- Pydantic v2 contracts for HealthPolicy, RateLimitPolicy, and ToolManifest;
- a thread-safe in-memory ToolRegistry with exact version lookup, exact capability discovery, duplicate protection, deterministic listing, and defensive copies;
- unit tests for invalid metadata, credential-reference handling, execution-mode declarations, and registry behavior.

It intentionally does not add a dispatcher, execute an adapter, change Nexus registrations, migrate Telegram/Drive, or convert YAML pipelines. Those changes depend on the authorization and execution contracts above.

## Consequences

### Positive

- Establishes one provider-neutral manifest shape without disturbing existing connectors.
- Prevents catalog metadata from being mistaken for executable permission.
- Makes tool identity/version deterministic for future routing and audit.
- Gives Global Intelligence (#679) a stable dependency boundary without embedding HTTP clients or provider SDKs in its agents.

### Trade-offs and deferred decisions

- The registry is process-local and must later be populated by a versioned source of truth.
- Health probes, schema instance validation, authorization, adapter binding, dispatch, persistence, and toolchain execution are not delivered by this increment.
- A future dispatcher must choose a supported JSON Schema validator and define limits for schema size, reference resolution, recursion, and validation time.
- Existing adapter APIs and pipelines remain in place until compatibility tests cover each migration.

## Validation

The implementation is covered by tests/domain/test_tool_registry.py. CI must run the targeted tests and the repository's full pytest workflows. No production connector, credential, device, or external service is touched.
