# Declarative execution plans

## Scope

The interpreter composes existing Jarvis connectors through a bounded, declarative plan. It is not an arbitrary-code sandbox, a new agent role, a policy authority, or a durable workflow engine.

## Plan shape

A plan uses version `1`, a stable `execution_id`, and a non-empty ordered list of steps. Each step has a unique `step_id`, a registered `tool`, JSON object `args`, optional earlier-step `depends_on`, and optional `output_fields` projection.

A value such as `{"$ref":"lookup.item_id"}` explicitly references a field from an earlier step. Every referenced step must be declared in `depends_on`. References are data references only; strings are never evaluated as expressions. This version supports no loops or dynamic branches.

## Runtime guarantees

- Validate the entire plan before connector dispatch.
- Reject unknown fields, duplicate IDs, invalid dependency order, unsupported versions, oversized plans, and non-JSON values.
- Enforce a host-configured executor allowlist. A plan cannot register a tool or provide executable code.
- Call the injected policy gate immediately before each step. `allow` is the only decision that dispatches; `approval_required`, denial, or policy failure stops the plan.
- Stop on the first failure. No automatic retries are performed.
- A connector exception after dispatch yields `unknown`, because an external operation may have happened before the error. Reconcile state before proposing another execution.
- Project results to requested fields and enforce a maximum serialized result size before exposing them to downstream steps.
- Return per-step status and duration for evidence and telemetry.

## Deliberate limitations

This is a deterministic, in-process interpreter with a synchronous injected executor. Optional event-sink hooks can record lifecycle events; they are only durable if the host supplies an append-only durable sink. The interpreter fails closed if journaling fails before dispatch and reports `unknown` if it cannot record a result after a possible side effect. Lifecycle events omit raw argument values and tool result payloads; they include only operational metadata. The elapsed-time budget is checked between steps and cannot preempt a currently running synchronous connector. Cross-process replay protection, pause/resume after approval, operation-level idempotency, hard connector timeouts, and conditional branching are still absent. Do not use it for production mutations until those controls are integrated with the real policy gateway and durable state store.

Desktop actions must continue to use the existing verified visual-navigation adapter, which handles ambiguity, postconditions, and observations.

## Rollout

1. Unit-test plan validation and deterministic execution using fake connectors.
2. Integrate a small, read-only connector allowlist and benchmark against direct tool calls.
3. Connect the event sink to a durable journal, then add replay protection, explicit approval resume, idempotency/reconciliation, and hard connector-call/time budgets.
4. Only then consider mutating connectors and desktop recipe composition.


## TaskRunner / Nexus integration

`TaskRunner.execute_plan({"plan": ..., "user": ...})` now provides the runtime seam for declarative plans. It snapshots the host-configured `CapabilityAuthorizer` allowlist, resolves each capability through the real Nexus registry immediately before dispatch, and calls that capability's existing `execute(context)` entry point. Plans cannot supply Python callables or add capabilities to the allowlist.

The existing authorizer is invoked per step. A sensitive-capability confirmation failure becomes `approval_required`; other authorization failures stop before dispatch. The host must inject `plan_event_sink` into `TaskRunner`. If it is absent, execution is rejected. The sink must be backed by durable append-only storage in production; the integration layer cannot infer durability from a callback.

This is an explicit API seam, not proof that every natural-language assistant request is automatically converted into a plan. Existing legacy task execution remains unchanged. Before enabling plans in production, wire the host's durable journal and caller identity into TaskRunner construction, then exercise the complete request-to-plan-to-Nexus path in deployment-level tests.
