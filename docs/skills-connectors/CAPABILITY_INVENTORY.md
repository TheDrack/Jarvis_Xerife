# Jarvis Capability Inventory for Agents

**Scope:** repo-derived discovery map for compatible agent harnesses.  
**Source of truth:** source code, tests, live connector registry, deployment state, and the delivery audit—not the status field alone.  
**Last reviewed:** 2026-11-03 (repository implementation, CI and connector discovery review; not a complete production runtime audit).

## How to interpret status

- **Implemented (code):** a code path exists; this does not prove it is connected or correct.
- **Available in session:** the current agent's live host registry exposes the needed tool/connector.
- **Authorized:** the current principal and host policy permit this specific action.
- **Tested:** relevant tests or repeatable probes pass; name the evidence.
- **Production-verified:** observed against the actual deployed service/device/database with timestamped evidence.
- **Partial / unverified:** some wiring exists but acceptance evidence is missing.
- **Stub / metadata-only:** an inventory entry or placeholder exists without proven behavior.

Never infer the latter states from file names, README claims, inventory metadata, or the presence of a skill.

## Agent-facing capabilities

| Capability | Repository entry points | Evidence / limitation to disclose |
|---|---|---|
| Universal Tool Registry (metadata layer) | app/domain/tools/contracts.py, app/domain/tools/registry.py, ADR-001 | Canonical process-local registry with versioned ToolManifest snapshots, exact capability lookup, schema validation, duplicate protection and compatibility loading. Registry membership does not prove adapter health, authorization or execution. |
| Common skill and connector bootstrap | docs/skills-connectors/CATALOG.md, CONTEXT_MEMORY_PROTOCOL.md, skills/*/SKILL.md | Portable guidance is present. Whether every harness automatically reads it at conversation start must be verified per host. |
| Multi-agent leader/scheduler contracts | app/multiagent/contracts, scheduler/leader/transport modules; [platform design](../architecture/jarvis-multi-agent-platform.md) | Cost-benefit scheduler and task-scoped roles are documented; real multi-runtime end-to-end execution, supervision, heartbeat, and lease renewal remain acceptance items in the architecture document. |
| Durable task/message queue | Supabase queue adapter and migrations 202610230002–202610230004 | Repo has adapter/migrations; do not assume these migrations are applied to production without checking the target project's migration history. |
| Declarative execution plan | app/multiagent/execution_plan.py, app/application/services/task_runner.py, orchestrator_service.py | Structured plans only; allowlist and journal required. Sensitive actions stay blocked until trusted approval/resume is implemented. |
| Append-only execution-plan journal | app/adapters/infrastructure/supabase_plan_journal.py, migrations 202610260002 and 202610270002 | Code and migration exist. Runtime insert through the deployed adapter is not verified by this document. |
| Capability inventory and Nexus discovery | data/capabilities.json, app/core/nexus.py, discovery and capability manager services | Metadata needs auditing: the historical delivery audit found 78/102 capability files were stubs and none of the capability IDs were exercised by tests at that audit point. Treat counts as historical until rerun. |
| Auto-evolution | EvolutionOrchestrator, EvolutionGatekeeper, EvolutionSandbox, scripts/evolve_all_pending.py | Audit documented gaps in protected paths and discovery of already-existing implementations. Auto-evolution should remain opt-in/paused until current gates and tests are confirmed. |
| Self-healing CI | scripts/jarvis_healer.py, workflow files | Historical CI runs show automated recovery workflow exists; every claim must be tied to the specific current run and its outcome. |
| YAML pipelines | config/pipelines/*.yml, app/runtime/pipeline_runner.py | Legacy Nexus steps remain supported; explicit tool_id steps route through ToolDispatcher and can receive approval only from trusted runtime parameters. Automatic pipeline generation and full legacy migration are not delivered. |
| Universal Toolbox / toolchains | app/runtime/toolbox/, config/tool_registry.json, config/toolchains/*.json | Registry, typed manifests, JSON Schema argument/output validation, principal/session/tool-bound authorization gates, adapter resolution, process-scoped idempotency, per-process timeout/rate-limit/circuit breaker, JSONL event sink, provenance-aware EvidenceRecord, and budgeted DAG execution with read-only retry are implemented in the current development branch. Dispatch requires a principal/session/tool-bound authorization policy; no production policy is wired yet, so live dispatch remains fail-closed. Focused tests pass; distributed idempotency/quotas, remote provider health checks, shared audit persistence, in-flight synchronous cancellation and all-adapter migration remain incomplete. Not production-verified. |
| Universal Intelligence public feeds and provider adapters | app/domain/intelligence/, app/application/ports/intelligence_observation_source.py, app/adapters/infrastructure/intelligence/, config/tool_registry.json, data/nexus_registry.json | GDELT DOC, NASA EONET and USGS read-only adapters plus IntelligenceCore and separate event/observation contracts are integrated. Optional GEV MCP adapter provides bounded read-only aircraft/vessel/satellite observations; OSIRIS REST adapter in main covers earthquakes, NASA FIRMS fires and public news. PR #693 and #694 full suites: Linux and Windows each 2106 passed, 12 skipped on the latest adapter revision. PR #694 merged OSIRIS weather alerts from NASA EONET, NOAA/NWS and GDACS; NOAA polygon centroids are not represented as exact points. USGS/EONET event IDs are aligned across adapters for deterministic deduplication. GEV/OSIRIS remain opt-in and are not live-connected, Nexus-registered, scheduled or persisted; no production authorization is inferred. Durable history, briefing, scheduler/delivery and map remain pending. |
| Desktop UI automation | app/adapters/edge/jarvis_desktop_mcp.py, jarvis_desktop_cli.py, visual navigation skill | Requires Windows interactive session, installed edge dependencies and an exposed local/remote bridge. Validate on the actual host. |
| Browser portas and traffic observer (CDP) | app/adapters/edge/portas_*.py, data/portas/macros | Implemented on PR branch; unit tests cover macro authorization, URL scheme allowlisting, URL/payload redaction and WebSocket event callbacks. CI integration test attaches to Chromium/CDP and captures HTTP events. WebSocket frames via real CDP and the user's persistent browser profile remain runtime acceptance items. |
| Android navigation | skills/jarvis-android-navigation/SKILL.md and Android-related modules/workflows | Skill exists; paired device and end-to-end hardware behavior must be checked live. |
| LLM routing and cost tracking | llm_router, model/gateway adapters, CostTrackerAdapter | Cost tracking is documented as consumed by the router; provider availability/credentials are runtime-dependent. |
| Context/memory | memory services/adapters and context protocol | Code does not prove persistence backend is connected or that provider-native memory changed. Confirm writes and readback. |
| Remote access | [RDC → Aperture → Tailscale → Jarvis runbook](../ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md) | Installation-specific route. Validate live connector, grants, tailnet and interactive Windows session. |
| GitHub / Supabase / Render operations | Connector families listed in [CATALOG.md](CATALOG.md) | The current AI agent can use only tools actually exposed by its connected host and authorized account. |

## Known gaps that affect agent selection

1. **Capability metadata is not behavioral proof.** The delivery audit dated 2026-10-16 reports 102 capability files, 78 stubs, and no tests exercising the cap_0XX/Cap0XX identifiers at that audit point. Re-run the audit before using the count as current.
2. **AdapterRegistry production consumption:** the same audit reported no production consumer at that point, despite working registry methods.
3. **Existing-code-first evolution:** the audit found all 34 then-pending capabilities already had files, so evolution could duplicate existing code.
4. **DockerSandbox:** code existed but no production consumer/test was found in that audit; do not promise container isolation by default.
5. **Security authorization coverage:** the audit found the main AssistantService → Executor path was not consistently routed through CapabilityAuthorizer. Check current code before assuming a universal authorization boundary.
6. **Protected mutation paths:** the audit found auto-evolution protections did not cover all required infrastructure/security paths. Keep evolution gated until current tests prove the boundary.
7. **Declarative plans:** unknown outcomes after a connector dispatch must not be blindly retried. Sensitive capabilities remain blocked pending trusted approval/resume.
8. **Production state is separate from repo state:** deployment, migration, connector connectivity, device availability, and service-role access each require live evidence.

## Roadmap rule

The canonical progress table is in [STATUS.md](../STATUS.md). Only mark an item complete when its acceptance criteria are supported by repository changes and passing tests; production-facing items additionally require deployment/runtime evidence. Do not convert a proposed feature, a capability inventory flag, or a merged PR into a completed production capability.
