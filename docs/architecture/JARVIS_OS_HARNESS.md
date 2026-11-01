# Jarvis OS — Harness Architecture

**Status:** Architecture baseline for JOF 0.1  
**Decision:** evolve `Jarvis_Xerife` into the Jarvis harness and add optional host/OS layers.  
**Execution modes:** portable harness, autonomous harness, host integration, installable Jarvis OS.  
**LLM policy:** provider-neutral; no model or provider is mandatory.

## 1. Core decision

Jarvis OS is not a second application that duplicates Jarvis_Xerife. It is the optional operating-system distribution and host-management layer built around the existing Jarvis harness.

The repository remains useful without installing an operating system. Users opt into capabilities and integration levels. Installing the OS layer must never be a prerequisite for using the portable harness.

The harness owns orchestration, capability discovery, policy enforcement, task state, agent coordination, audit, and adapters. It does not own or require a particular source of intelligence.

## 2. Layered architecture

```text
User surfaces
  Desktop / Web / Mobile / Voice / CLI / External agent runtimes
                         |
Interaction and intent boundary
  API / WebSocket / Intent normalization / Session context
                         |
Portable Jarvis Harness
  Nexus DI / Capability registry / Skills & connector catalog
  Memory contracts / Policy interfaces / Audit / Event contracts
                         |
Agent and model orchestration
  Provider adapters / Model capability registry / LLM router
  Multi-agent scheduler / Task and message queues / Worker runtimes
                         |
Execution boundary
  Capability authorizer / Declarative plans / Execution journal
  Sandboxes / Tool adapters / Privileged operations broker (optional)
                         |
Optional host integration
  Hardware discovery / Resource manager / Device manager
  Service supervisor / systemd units / Desktop integration
                         |
Optional Jarvis OS image
  Linux base / boot / installer / recovery / update channel
```

The portable harness must remain usable with only the first four software layers. Host integration and the OS image are opt-in extensions.

## 3. User-selectable operating profiles

Profiles are additive and capability-gated. Selecting a profile must not silently grant new permissions.

| Profile | Purpose | Requires OS installation |
|---|---|---:|
| `harness` | Portable Python harness, skills, connectors, adapters, memory interfaces, and user-provided LLMs | No |
| `autonomy` | Planning, multi-agent execution, task queue, supervision, policy and auditable automation | No |
| `host` | Optional integration with the host OS, hardware inventory, resource telemetry and managed services | No; requires explicit host permissions |
| `jarvis-os` | Reproducible Linux installation with boot services, desktop and recovery tooling | Yes |

Profile activation is explicit. The runtime must report requested, available, enabled, authorized, and tested capabilities separately.

## 4. Provider-neutral intelligence boundary

No orchestration component may depend directly on a provider SDK or provider-specific environment variable. Provider-specific behavior belongs in adapters.

A normalized model profile should describe at least:

- stable agent/model identifier and provider identifier;
- endpoint/runtime kind (remote API, local runtime, external agent);
- supported modalities and capabilities (text, vision, audio, tools, structured output);
- context and output limits when known;
- availability/health and concurrency;
- measured latency, reliability, and estimated cost when known;
- data-handling and trust classification;
- required credentials by reference/name only, never credential values.

The invocation contract must normalize request, response, usage, errors, timeout, cancellation, and correlation identifiers. Provider-specific extensions may exist, but must not be required for generic scheduling.

Existing Groq, Gemini, Venice, Respan, Ollama, and FreeLLMAPI paths are adapters/integrations to be reconciled, not replaced in this milestone. Existing task-specific behavior must be preserved until a compatibility test proves the new route.

The current repository includes provider-specific defaults and task routing in `AIGateway` and `LLMRouter`. These are known coupling points to progressively move behind provider/model capability registration. This document does not claim that provider neutrality is already implemented.

## 5. Multi-agent execution

The scheduler selects agents by task requirements and measured properties, not permanent model roles.

Each agent advertises a runtime profile with:
- supported tools/capabilities;
- model/provider identity;
- modalities and structured-output support;
- availability, concurrency and current load;
- cost, latency and measured success rates;
- trust boundary and execution environment.

Task assignment is capability-first. Provider-specific constraints are allowed only when a task explicitly requires them and the reason is recorded. Otherwise, any eligible provider may execute the task.

Multiple agents may run simultaneously. Shared task state must use durable task IDs, attempt IDs, leases/fencing, idempotency keys, explicit acknowledgements, bounded retries and audit events. Delivery is treated as at-least-once; external effects must be idempotent or require approval.

A single provider failure must not disable other configured providers. A model is not considered available merely because its adapter is installed; credentials, endpoint health, policy and capability checks must pass.

## 6. Autonomy and privileged host operations

Autonomy is adaptive, not unrestricted.

The default flow is observe → diagnose → propose → stage → validate → promote → monitor, with rollback evidence. The policy engine evaluates identity, capability, scope and risk.

Portable harness operations run without OS administrator privileges. Host-level actions are exposed through a separate optional broker with typed operations and narrow allowlists. The broker must not execute arbitrary shell text supplied by an LLM.

Critical operations (bootloader, kernel, firmware, firewall, identity/permissions, destructive storage actions, secrets and production deployments) require explicit human authorization according to policy.

Agents that propose a change must not be the sole validators of that change. Deterministic tests and independent checks are required.

## 7. Fault isolation and degraded operation

- Desktop failure must not stop the core harness.
- Agent failure must not stop other workers.
- One provider outage must not stop other providers.
- Loss of internet must not prevent local diagnostics and locally available tools.
- Queue/database outages must be explicit; do not simulate successful shared coordination with an in-memory fallback.
- Host supervisor and recovery must remain operable if the Jarvis intelligence layer fails.
- Configuration and OS updates must be versioned, reproducible and rollback-capable.

## 8. Existing repository mapping

| Existing subsystem | Target responsibility | Treatment |
|---|---|---|
| Nexus DI / discovery | Component lifecycle and dependency resolution | Reuse; define stable public contracts |
| AdapterRegistry / capability manager | Capability discovery | Reuse, audit behavior and integrate into execution path |
| AIGateway / LLMRouter / model adapters | Provider/model invocation and selection | Preserve compatibility; progressively decouple provider policy |
| Semantic/procedural/working memory | Memory backends | Reuse behind provider-neutral interfaces |
| app/multiagent contracts/scheduler/transport | Multi-agent orchestration | Reuse; complete real-runtime supervision and acceptance tests |
| Supabase task/message queue | Optional durable shared coordination | Keep backend optional; local standalone mode needs an explicit local backend |
| TaskRunner / declarative execution plans / journal | Structured execution and audit | Reuse; maintain fail-closed authorization |
| EvolutionGatekeeper / EvolutionSandbox | Staged change validation | Reuse after protected-path and isolation audit |
| FastAPI / WebSocket / desktop/mobile surfaces | User and runtime interfaces | Reuse; separate API lifecycle from desktop lifecycle |
| systemd, hardware and desktop integration | Host/OS management | New optional layer; never imported by portable harness |

The documentation inventory is not proof of runtime behavior. Each mapping must be checked against source and tests before code is moved or duplicated.

## 9. Non-goals for JOF 0.1

- Do not embed, download or require a local LLM.
- Do not choose a permanent primary LLM vendor.
- Do not rewrite the existing harness or replace working adapters.
- Do not require Supabase, Render, Docker, a GPU or internet for basic harness startup.
- Do not grant agents root access.
- Do not produce or flash a bootable image before the base OS, boot, driver and recovery tests exist.
- Do not change production databases, credentials, network policy or deployed services as part of the initial foundation.

## 10. Acceptance criteria

1. Harness profile can be installed and used without OS-specific services.
2. Autonomy and host profiles are opt-in and permission-gated.
3. Model/provider adapters can be registered without editing the core scheduler.
4. At least two different provider/runtime adapters can coexist in one agent registry.
5. Scheduler eligibility is based on declared task/model capabilities, not a hard-coded default provider.
6. Multiple workers can process distinct tasks concurrently with durable attempt/lease semantics.
7. A provider outage is isolated and reported without falsely marking the task completed.
8. Portable harness tests run in a clean Linux virtual environment.
9. OS-specific dependencies are optional and absent from the core install.
10. No existing tests are removed, skipped, weakened or disabled to obtain a green result.
