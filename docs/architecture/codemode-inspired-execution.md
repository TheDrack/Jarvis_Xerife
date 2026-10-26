# Code Mode-inspired execution for Jarvis

## Objective

Reduce model/MCP round trips and redundant context while preserving Jarvis's existing authorization, evidence, and recovery boundaries. This is an architectural adaptation, not a copy of Cloudflare Code Mode.

## Existing capabilities to reuse

- The Harness and connector catalog already expose tools through MCP and other adapters.
- The desktop MCP server already offers `run_visual_recipe`, a bounded sequence of clicks with per-step postconditions.
- Visual navigation prefers UI Automation where possible, rejects ambiguous image matches, limits recipes to 20 steps, and can stop with a screenshot when a target or postcondition is uncertain.
- The multi-agent control plane documents at-least-once delivery, correlation IDs, idempotency, fencing, and recovery requirements.

## Changes in this increment

1. A visual recipe's semantic postcondition must represent a transition: the count of matching visible accessibility elements must increase from its pre-action baseline. An already-visible label no longer proves the new click succeeded.
2. If the semantic baseline cannot be observed and no visual postcondition is available, fail closed before sending input.
3. If the semantic postcondition was already present and no new occurrence appears, return `postcondition_preexisting`, preserve the completed-step list and attach an observation. Do not automatically repeat the action.
4. The desktop MCP wrapper no longer attaches a redundant final screenshot to a recipe that completed with every step verified. Failed or uncertain recipes continue to include visual evidence. This reduces image/context payload without removing the evidence needed for recovery.

## Proposed execution model

The long-term equivalent of Code Mode should be a bounded execution-plan interface over existing Jarvis tools, not arbitrary generated Python running inside the trusted process.

### Plan contract

A plan should be declarative and versioned, with:
- stable `execution_id` and per-step `step_id`;
- an allowlisted connector/tool name and schema-validated arguments;
- bounded step count, elapsed time, output size, and connector-call budget;
- explicit dependency edges and simple branch predicates over structured results;
- per-step policy classification (read, reversible write, irreversible write, desktop input);
- optional idempotency key and declared postcondition;
- compact result projection, retaining large artifacts by reference;
- execution status and evidence references for each step.

Do not accept raw `eval`, `exec`, dynamic imports, arbitrary filesystem access, or unrestricted network access as a first implementation. If an actual code sandbox is later justified, it must be an independently isolated executor with no credentials; all capabilities must pass through the same host-side policy gateway.

### Runtime invariants

1. **Authorization is enforced at the host boundary.** The plan is not an authorization grant. Check every tool call using the active task identity, least-privilege scope, and current policy.
2. **Separate execution from result handling.** Store the full tool result/evidence in the execution journal when appropriate; return only fields required by downstream steps and the final model response.
3. **Never confuse replay with re-execution.** A recorded successful step can reuse its result. A step with an ambiguous outcome is `unknown` until reconciled; never retry an external side effect blindly.
4. **Idempotency is per operation.** Use connector-supported idempotency keys where possible. Desktop clicks are not generally idempotent; reconcile the observed UI state before any retry.
5. **Verification belongs to the tool contract.** A successful transport response is not proof that the intended state change occurred. Each mutating tool must return a verifiable outcome or an explicit uncertain status.
6. **Pause before protected effects.** An approval-required step pauses the execution; after approval, resume from durable state without repeating completed steps.
7. **Bound resource use.** Enforce per-plan limits for steps, tool calls, wall-clock time, returned bytes, and nested fan-out. Reject oversized plans before any side effect.
8. **Treat tool output as untrusted data.** Output may inform branch conditions but cannot modify the plan's authority, policy, or tool allowlist.
9. **Preserve observability.** Record execution/step IDs, tool names, timings, retry counts, status transitions, and evidence references; redact secrets and sensitive payloads.
10. **Keep direct tools for simple actions.** Use programmatic composition only when it reduces round trips or enables meaningful branching; simple one-off calls remain direct.

## Desktop navigation integration

Desktop automation should remain a domain-specific connector, not raw mouse access exposed to the generated program.

The plan may call a bounded operation such as `run_visual_recipe`. The existing adapter remains responsible for template uniqueness, semantic-first invocation, opt-in physical fallback, postcondition verification, and stopping on uncertainty. A plan must not automatically retry a click when the postcondition fails. It should return the observation and require reconciliation or a new plan.

For higher reliability, future work should add explicit precondition/postcondition contracts for each recipe step, including state-change verification for persistent labels and a way to reconcile `unknown` outcomes. Prefer UI Automation/DOM semantics over pixels when the target application exposes reliable controls.

## Efficiency measurement

Compare direct tool calling against bounded plans using equivalent tasks and record:
- model round trips;
- input/output tokens, including images;
- MCP calls and bytes transferred;
- median and p95 end-to-end latency;
- verified completion rate;
- false-positive verification rate;
- duplicate side effects and recovery cost.

Do not infer success from token reduction alone. A change is accepted only if efficiency improves without degrading verified completion or safety.

## Rollout stages

1. Harden existing batch operations and remove redundant successful-result payloads. **Implemented in this increment; CI validation pending.**
2. Add a pure, schema-validated plan contract and deterministic interpreter with fake connectors and adversarial tests.
3. Add a policy gateway, durable execution journal, idempotency/reconciliation rules, and approval pause/resume.
4. Integrate the plan interpreter with a small allowlisted MCP subset; benchmark against direct calls.
5. Add desktop recipe composition only after replay and uncertain-action recovery are covered by tests.

No generic arbitrary-code executor is introduced by this increment.
