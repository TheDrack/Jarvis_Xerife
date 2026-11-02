# ADR: Universal Toolbox and Tool Dispatch

**Status:** Accepted for incremental implementation
**Date:** 2026-11-02
**Related:** GitHub issues #680 and #679

## Context

Jarvis already has Nexus dependency injection, concrete adapters, a capability authorizer, and sequential YAML pipelines. These mechanisms are useful but do not form one execution contract: the AdapterRegistry is descriptive, and the legacy PipelineRunner resolves a component and invokes execute() directly.

Creating another adapter framework or replacing Nexus would duplicate infrastructure and risk breaking working integrations.

## Decision

Introduce a provider-neutral toolbox at app/runtime/toolbox with four distinct responsibilities:

1. **Manifest / Registry:** versioned tool IDs, capabilities, provider/origin/trust metadata, dependencies, permissions, adapter binding, JSON Schema input/output contracts, risk classification, scope allowlists, execution limits, and idempotency declaration.
2. **Dispatcher:** validates arguments, checks scope and policy-verified approval for active/intervention tools, calls the dedicated ToolAuthorizationPolicy port, resolves the adapter through Nexus, checks adapter preconditions, enforces process-local timeout/rate-limit/circuit-breaker policies, dispatches the declared operation, and emits a secret-free execution event with a request fingerprint.
3. **Adapter:** remains the provider-specific implementation. The registry does not instantiate providers or hold credentials.
4. **Toolchain / Workflow:** typed step manifests form a bounded dependency DAG with explicit result bindings, abstract cost budget, cancellation checks, and safe read-only retries. Existing YAML pipelines remain backward compatible during migration.
5. **Evidence:** EvidenceRecord captures source/provider, publication and observation timestamps, license, content hash, transformations, corroboration links, and confidence. ToolResult references evidence by ID rather than embedding raw source content.

Nexus remains the dependency-injection container. The Tool Registry is not an authorization system, and registration does not prove runtime health or connectivity.

## Initial compatibility surface

The checked-in registry exposes five atomic tools:
- telegram.get_updates as read-only, without exposing the offset parameter that acknowledges/consumes updates.
- telegram.send_message as active, requiring a policy-verified approval reference and an idempotency key; the Toolbox wrapper can only target the configured Telegram chat.
- drive.upload_backup as active, requiring a policy-verified approval reference and an idempotency key; the adapter only uploads the canonical repository snapshot `CORE_LOGIC_CONSOLIDATED.txt`, never an arbitrary caller-supplied path.
- network.get_interfaces as read-only local interface inventory.
- network.discover_devices as read-only ARP-cache inspection limited to an RFC1918 /24 or smaller; it sends no probes.

The Toolbox uses DriveUploader.upload_backup_scoped(context), restricted to the canonical snapshot. The legacy upload_backup(context)/execute(context) path remains unchanged for existing trusted pipelines; it is not the bounded Toolbox capability. The Telegram adapter reports local token readiness through can_execute(); this does not claim a successful remote API health check.

## Security and execution semantics

- Input arguments are validated against Draft 2020-12 JSON Schema before adapter resolution.
- The dispatcher accepts only a dedicated `tool_authorization_policy` port. The legacy CapabilityAuthorizer is not a trusted principal/approval provider and is rejected for tool execution.
- The policy decision must bind authenticated principal, session, tool ID/version, capability, scope, operation, expiry and correlation ID. Active/intervention operations additionally require an approval reference verified by that policy and bound to the exact request; a caller-provided ID is not itself proof of approval.
- The `caller` field is an untrusted label and is not used as identity. The old `human_confirmed` boolean was removed from ToolRequest. Manifest scope patterns are checked before adapter resolution.
- idempotency_mode=process keys cached executions by tool ID, exact tool version, declared capability, and idempotency key; the request digest binds arguments, authenticated principal, and scope. It detects key conflicts, authorizes before returning a cached result, and prevents blind replay of active calls with unknown outcomes. State is bounded and process-local, not durable/provider-side exactly-once delivery.
- Manifest timeout, per-process sliding-window rate limit, circuit-breaker threshold/reset, and abstract cost units are enforced by the dispatcher/toolchain runner. These controls are process-local, not distributed quotas.
- Toolchains support a bounded step count, dependency DAG, explicit output bindings, execution budget, cancellation checks between steps, and retries only for explicitly retryable read-only calls. Active/intervention calls are never automatically retried.
- Audit events contain identifiers, version, caller, scope, status, timestamps, latency, and error code; they intentionally omit raw arguments, outputs, headers, and secrets. The JSONL sink is append-only on the local filesystem, not a shared durable journal.
- Provider errors and false/empty results are not promoted to successful execution. A timeout/exception after starting an active operation is classified as outcome-unknown and cached to block a blind replay.

## Deliberate limitations of this increment

- Idempotency, rate limiting, circuit breaker, and audit are process/local-filesystem scoped; no distributed lease, shared idempotency store, or shared durable audit journal yet.
- No claim of remote provider health from manifest presence or local credential presence. Adapter preconditions are local readiness checks only.
- Cancellation is observed between toolchain steps/retries; it cannot forcibly stop a synchronous provider call already running in a worker thread.
- Retry is restricted to explicitly retryable read-only operations; active/intervention retry/compensation remains disabled.
- Legacy pipeline steps are not automatically migrated; their behavior remains unchanged.
- No production `tool_authorization_policy` is registered yet. Until a host-backed principal/session resolver and approval verifier are implemented, all real dispatch attempts fail closed; the tests use an explicitly test-only policy double.
- GitHub, Supabase, Render, browser, network, and other connectors remain migration targets; they are not declared universalized by this first registry.

## Consequences

The initial dispatcher defines one validated execution boundary for the first communication/storage adapters without rewriting Nexus or breaking the current pipeline contract. It fails closed unless the host registers a trusted ToolAuthorizationPolicy; no production policy is wired in this increment. Future migrations must add contract tests and runtime evidence per adapter family.
