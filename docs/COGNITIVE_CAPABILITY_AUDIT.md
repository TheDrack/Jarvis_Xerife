# Cognitive Capability Audit — 2026-11-23

## Purpose and evidence standard

This audit establishes the current implementation and runtime state before autonomous roadmap work is enabled. It uses Graphify definitions/callers/dependencies, repository consumers, regression tests, workflow runs, Termux process state, and Supabase records.

A module name, class, README, test fixture, or green CI run is not proof of an operational capability. The classifications below distinguish:

- **Integrated** — a production caller reaches the implementation.
- **Partial** — a production path exists, but one or more required stages or contracts are disconnected.
- **Isolated** — implementation and tests exist, but no production caller was found for the relevant operation.
- **Inactive** — the implementation exists, but its runtime service/feature is not active.
- **Blocked** — an explicit missing capability, credential, permission, or roadmap gate prevents execution.

Tests prove the tested behavior only. They do not independently prove production wiring or end-to-end execution.

## Executive finding

Jarvis is not missing all of the cognitive components. It has several useful subsystems, but they do not yet form one closed cognitive loop:

`observe → normalize → resolve identity → update world model → consolidate memory → reason → plan → execute tools → verify effects → learn`

The strongest live path is the Termux worker's authenticated queue connection and remote LLM inference. It is healthy, but it advertises only `text_reasoning`. The two real tasks waiting in Supabase require repository, GitHub, and production-read capabilities, so neither is eligible for that worker.

The roadmap is separately blocked: the mission manifest is empty, all C0 evidence-ledger criteria remain pending, and the latest scheduled evolution run was paused because `EVOLUTION_ENABLED` was empty. Consequently, the scheduled workflow skipped both isolated generation and privileged publication.

## Capability map

| Roadmap domain | Existing implementation | Production path and tests | Classification / gap |
|---|---|---|---|
| **Perception / observations** | `app/application/services/intelligence_core.py`, `intelligence_collector.py`, `intelligence_recurring_worker.py`; adapters under `app/adapters/infrastructure/intelligence/` for God’s Eye, Osiris, public intelligence, and Supabase history | Dashboard/collection routes call the collector and core. `main.py` can start the recurring worker when its feature flags are enabled. Tests include `tests/application/test_intelligence_core.py`, `test_intelligence_collector.py`, `test_intelligence_observations.py`, `test_intelligence_recurring_worker.py`, and adapter tests. | **Partial.** Source ingestion and normalized observations exist. The recurring worker persists history, but it does not project observations into the graph world model. Its recurring runtime is feature-flagged. |
| **World Model** | `app/domain/graph/` contracts and algorithms; `app/adapters/infrastructure/graph/graph_store.py`; `app/application/services/graph_store_setup.py`; `app/application/services/graph_enrichment.py` | OSINT MCP tools reach `GraphStore.upsert_delta`. Tests include `tests/domain/graph/`, `tests/adapters/infrastructure/graph/test_graph_store.py`, and `tests/application/test_graph_enrichment.py`. | **Partial / isolated.** Graph storage is used by OSINT tools. `GraphEnrichmentService.enrich_scope` has no production caller, and `GraphStore.upsert_delta` is not called by the recurring intelligence worker. The observation-to-entity bridge is missing. |
| **Cognitive Memory** | `app/domain/memory/` working, semantic, and prospective memory; `app/application/services/memory_manager.py`; `memory_consolidation_service.py`; vector/procedural adapters; `app/multiagent/objective_journal.py` | Assistant-router memory scope and the worker objective journal have consumers. Tests include `tests/application/test_memory_manager.py`, `test_memory_consolidation_service.py`, `tests/adapters/infrastructure/test_vector_memory_adapter.py`, `test_procedural_memory_adapter.py`, and `tests/multiagent/test_objective_journal.py`. | **Partial.** Session/procedural memory and the worker's local journal are present. `MemoryConsolidationService.execute` and `SemanticMemory.execute` have no production caller in the indexed call graph. Long-term consolidation from observations/tasks is not a connected loop. |
| **Reasoning** | `app/multiagent/freellmapi_client.py`, `model_runtime_factory.py`, `priority_queue_mini_agent.py`; `app/application/services/llm_router.py`; `app/domain/services/intent_processor.py`; infrastructure AI gateway adapters | `AssistantService.process_command` reaches `IntentProcessor.execute`, which calls `llm_service` or `ai_gateway` for unknown conversational requests. The multiagent worker reaches its registered model runtime. Tests include `tests/domain/test_intent_processor.py`, `tests/multiagent/test_freellmapi_runtime.py` and `tests/test_llm_router.py`. | **Partial.** Production assistant inference and multiagent inference are integrated, but `LLMRouter.route` has no strict production caller. `CognitiveRouter` and `config/pipelines/jarvis_chat.yml` are isolated: no production caller invokes `run_pipeline("jarvis_chat")`, and the pipeline's `llm_engine` component has no verified implementation/consumer contract. The active assistant path is `IntentProcessor`, not this YAML pipeline; do not wire the incomplete pipeline into command execution as a second classifier. |
| **Strategic planning** | `app/application/services/task_runner.py`, `agent_task_queue_service.py`, `app/application/services/roadmap_mission_selector.py`, and the multiagent scheduler | `TaskRunner` has application callers, including the local agent and task-queue service. The roadmap selector is used by `.github/workflows/auto_evolution_triggerV2.yml`. Tests include `tests/application/test_task_runner.py`, `test_task_runner_navigation_plan.py`, `tests/multiagent/test_task_runner_execution_plan_integration.py`, and `tests/application/test_roadmap_mission_selector.py`. | **Partial.** Local task planning and the GitHub roadmap workflow are separate execution paths. Before this audit change, `AutoEvolutionServiceV2` and the HUD progress route still counted the legacy capability inventory instead of verified roadmap evidence. |
| **Autonomous execution** | `app/multiagent/worker_daemon.py`, `agent_worker_runtime.py`, `priority_queue_mini_agent.py`, `supabase_task_worker.py`; `app/adapters/infrastructure/routers/agent_tasks.py`; worker credential store | Render queue endpoints and the Termux daemon form a live heartbeat path. Tests include `tests/multiagent/test_worker_daemon.py`, `test_agent_worker_runtime.py`, `test_priority_queue_mini_agent.py`, and worker-identity/credential adapter tests. | **Partial / blocked.** Worker is online and authenticated, but only `text_reasoning` is advertised. No task can be claimed unless its required tools are a subset of that capability list. |
| **Tool execution and governance** | `app/runtime/toolbox/` dispatcher, registry, authorization policies, and adapters | Toolbox behavior has unit and integration tests under `tests/runtime/`. | **Isolated from the Termux queue.** The worker does not dispatch through this toolbox and does not expose `repository_read`, `github_read`, or `production_read`. Do not add those names to `available_tools` until their implementations and authorization checks exist. |
| **Android/mobile interface** | `app/adapters/edge/android_accessibility_client.py`; `JarvisAccessibilityService.kt` and the Android setup panel | The bridge exposes loopback-only snapshot, screenshot, and action endpoints protected by a paired token. Tests include `tests/adapters/edge/test_jarvis_android_accessibility_mcp.py` and Android workflow security tests. | **Inactive.** The Termux token exists with mode `600`, but no listener was present on `127.0.0.1:18766`. The ChatGPT, Claude, Gemini, Qwen, and Grok packages are installed. UI-backed inference cannot operate until the Android accessibility service is enabled and its live endpoint is verified. |
| **Roadmap evolution** | `RoadmapMissionSelector`, `AutoEvolutionServiceV2`, `scripts/evolve_all_pending.py`, and the integrated evolution workflow | The latest run, [45151249242](https://github.com/TheDrack/Jarvis_Xerife/actions/runs/45151249242), completed its gate successfully but skipped generation and publication. | **Blocked.** `data/roadmap_missions.json` has `missions: []`; `EVOLUTION_ENABLED` was empty. The application service and HUD must use the same evidence-ledger selector as the workflow, not legacy capability labels. |

## Runtime evidence — Android worker

Observed on 2026-11-23:

- Termux daemon process: PID `6598`, status `running`, `restart_count=0`, `last_error_type=null`.
- Supabase agent `jarvis-termux-mini-1`: `available`, provider `groq`, `active_tasks=0`, `concurrency_limit=1`, and `available_tools=["text_reasoning"]`.
- Local objective journal: `~/jarvis-mobile/state/agent-objectives.sqlite3`; `objective_journal` and `objective_steps` both contained zero rows.
- Supabase had two tasks in `ready` state: `prod-agent-audit-20261027-01` (priority 90) and `prod-agent-optimize-20261027-02` (priority 80).
- Both tasks require `repository_read`, `github_read`, and `production_read`. The Termux worker cannot claim them with its current capability list.
- The Termux environment contains the queue URL, worker identity token, and remote-inference configuration. It does not contain a local GitHub CLI login or local Render/Supabase credentials. The worker therefore depends on server-side inference and still lacks the read-only tool adapters required by the queued tasks.

A configuration checker returning `ready` means queue authentication and an inference route are configured. It does **not** mean that a task is eligible, that a task has been claimed, or that an objective has completed.

## Mobile LLM applications: API versus UI

The installed consumer applications are not API credentials. Their subscriptions/logins do not automatically provide developer API keys. The stable path is a provider API configured per agent; the alternative is a UI-backed adapter using the Android accessibility bridge and the user's already-authenticated app session.

The UI-backed route must:

1. Use only the visible accessibility tree, screenshots, and user-authorized UI actions.
2. Serialize access through one worker-process-wide lock; a single Android foreground UI cannot safely serve concurrent conversations from several agents.
3. Validate app identity, prompt submission, response completion, and response extraction before returning a result.
4. Treat app UI changes, quotas, sign-in state, and network delays as recoverable provider failures.

The accessibility token is already paired on the Termux side. The remaining prerequisite is enabling `JarvisAccessibilityService` in Android Accessibility Settings and confirming that `/healthz` responds on loopback.

### Implemented local-app provider path

The local model runtime now supports these installed app IDs behind one provider-neutral `ModelRuntime` adapter:

| Provider ID | Android package |
|---|---|
| `android_app:chatgpt` | `com.openai.chatgpt` |
| `android_app:claude` | `com.anthropic.claude` |
| `android_app:gemini` | `com.google.android.apps.bard` |
| `android_app:grok` | `ai.x.grok` |
| `android_app:qwen` | `ai.qwenlm.chat.android` |

The Termux worker can select a provider per agent using `JARVIS_AGENT_MODEL_PROVIDER_<AGENT_ID>` and `JARVIS_AGENT_REMOTE_INFERENCE_<AGENT_ID>`. For `jarvis-termux-mini-1`, the suffix is `JARVIS_TERMUX_MINI_1`. The Render API must receive the same server-side provider binding; it derives the provider from authenticated agent identity, not from an untrusted heartbeat claim. API-backed Groq/Venice/FreeLLMAPI and ChatGPT Plan runtime paths remain available and unchanged.

The UI adapter serializes all requests through one worker-process-wide lock, launches only allowlisted apps, rejects password/login screens and unrecognized editable fields, submits only through an accessible send control, and returns text only after the visible response stabilizes. It has no tool execution, file access, or action permissions. Consumer app sessions do not expose API keys; this is a local UI bridge, not a replacement for official APIs. App UI changes and quotas can still cause recoverable failures.

**Not yet runtime-verified:** the native service listener was not active at audit time, so no real prompt has been submitted to any consumer app. CI must build the Android APK, and the user must enable the accessibility service before a device smoke test. Do not switch the active Termux worker away from remote API inference until that smoke test passes.

## Recorded gaps and implementation order

1. **C0 — capability map and evidence ledger:** keep implementation, consumer, test, CI, and runtime evidence separate. Do not infer completion from legacy capability statuses.
2. **C1 — World Model observation bridge:** map normalized `IntelligenceObservation` records to stable graph nodes, preserve source/provenance/time/confidence, and persist idempotently through `GraphStore`. This is the first bounded roadmap mission.
3. **C2 — Perception:** make the recurring collection path observable and verify source health, deduplication, and history persistence.
4. **C3 — Cognitive Memory:** connect episodic observations and task outcomes to semantic consolidation, with provenance, retention, and retrieval tests.
5. **C4 — Reasoning:** connect the shared LLM router to production consumers and require evidence/contradiction-aware outputs where appropriate.
6. **C5 — Strategic Planner:** connect the roadmap selector and task planner to the shared queue with explicit dependencies and acceptance criteria.
7. **C6 — Autonomous Executive:** implement read-only repository, GitHub, and production tools with allowlists, scoped credentials, audit logs, and truthful capability advertisement before claiming the existing audit tasks.
8. **Mobile provider extension:** after accessibility activation, implement one tested adapter per installed app behind a serialized device broker. Keep API providers available as the preferred stable path.

## C0 acceptance interpretation

- `C0-CAPABILITY-MAP`: this document identifies code, production consumers, and tests for each critical domain.
- `C0-GAPS-RECORDED`: the disconnected call paths, inactive services, missing tools, and roadmap gate are listed explicitly above.
- `C0-NO-NAME-BASED-COMPLETION`: all classifications are based on callers, tests, workflow evidence, and observed runtime state. A module or legacy capability label alone never establishes completion.

The machine-readable ledger in `docs/STATUS.md` remains authoritative for completion. These criteria must stay `pending` until the audit is merged and its commit/check evidence is recorded there.

## Roadmap execution gate update

The machine-readable mission manifest now contains the first bounded C1 task, `C1-WORLD-MODEL`, with an existing implementation target and regression tests. The selector accepts prior-phase dependencies directly from the evidence ledger, so C1 does not need placeholder C0 code-generation missions. All three C0 criteria remain `pending`; therefore `find_next_mission()` correctly returns no mission today. Once the C0 audit PR is merged, its green Actions runs and consumer/test paths are recorded in `docs/STATUS.md`, the three C0 entries can be marked `verified` and the C1 mission becomes eligible without changing the selector again.
