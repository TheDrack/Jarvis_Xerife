# Proactive Initiative Engine

## Purpose

Add a user-scoped proactive loop to the existing AssistantService. The first vertical slice identifies:

1. **Temporal opportunities:** repeated successful user actions observed on distinct dates and near a stable local time.
2. **Help opportunities:** repeated command failures or explicit, user-scoped signals such as blocked tasks, approaching deadlines, stalled projects, repeated failures, and missing dependencies.

The engine produces a proposal and preparation context only. It does not execute tools, create tasks, change files, or assume permission to act.

## Open-source design references

- [OpenClaw](https://github.com/openclaw/openclaw): the heartbeat pattern inspired a periodic, low-noise evaluation cycle that stays silent when no useful initiative exists.
- [CORE](https://github.com/RedPlanetHQ/core): its personal-context and temporal-memory direction informed the use of user-scoped history, evidence references, and context-aware opportunities.
- MIRA, Khoj, and Serenity remain candidates for later study of companion workflows, retrieval, and memory consolidation; their code is not imported by this change.

These are architectural references only. No third-party source code was copied into Jarvis.

## Reused Jarvis components

- `AssistantService` remains the lifecycle and user-context boundary.
- `get_recent_hive_history(limit, user_id)` reuses the existing per-user interaction history.
- `NotificationService.communicate_user()` and `UserCommunicationService` provide presence-aware delivery and deduplication.
- `dispatch_to_mobile()` reuses the existing paired-device WebSocket/push transport; delivery is restricted to the configured `JARVIS_MOBILE_USER_ID`.
- Existing `Nexus` resolution is reused for notification delivery.
- Existing multi-agent queue, routine definitions, TaskRunner, and execution policies remain unchanged. The proactive loop does not create a second task scheduler or bypass the execution gate.

## Flow

```text
Authenticated user interaction ──> AssistantService records active user
                                           │
User-scoped domain event ──────────────────┤
                                           ▼
                              Proactive heartbeat (15 min)
                                           │
                         Load that user's recent history
                                           │
                                           ▼
                              ProactiveInitiativeEngine
                              ├── Temporal pattern detector
                              ├── Repeated-failure detector
                              ├── Explicit help-signal detector
                              ├── Relevance scoring
                              ├── Quiet-hours filter
                              └── Per-user cooldown / dedupe
                                           │
                                           ▼
                               Proposal + preparation context
                                           │
                          ┌────────────────┴──────────────┐
                          ▼                               ▼
                 Paired owner device               Not deliverable
                 presence policy allows             pending in memory
                          │                               │
                          └──────────────┬────────────────┘
                                         ▼
                           Existing mobile dispatch path
                                         │
                                         ▼
                            User decides whether to proceed
```

## Temporal inference

A temporal pattern is emitted only when all of these conditions hold:

- At least three distinct dates contain the same normalized successful command.
- Observations are within the configured history window (default 30 days).
- Current local time is within 35 minutes of the median observed time-of-day.
- The relevance score meets the configured threshold.
- The current time is outside quiet hours (default 22:00–07:00).

This is a conservative heuristic, not a learned probabilistic schedule. A pattern does not imply a calendar commitment. The message asks whether the user wants context prepared.

## Help detection

The engine recognizes these explicit signal kinds:

- `task_blocked`
- `deadline_approaching`
- `project_stalled`
- `repeated_failure`
- `dependency_missing`

Signals must include a non-empty `user_id`. Global/unscoped events are ignored to prevent cross-user notifications. A signal may include `title`, `objective`, `evidence_ref`, `confidence`, `impact`, `urgency`, `availability`, and `interruption_cost`.

Two or more identical failed commands within 24 hours also create a help candidate.

## Proposal contract

Every candidate includes:

- stable candidate key;
- kind, title, and user-facing explanation;
- bounded relevance score and confidence;
- evidence references;
- suggested timestamp;
- preparation objective and context;
- `execution_mode=proposal_only`;
- `requires_user_approval=true`.

Delivery is delegated to the existing `NotificationService.communicate_user()` path; no unauthenticated HUD WebSocket receives proposal content.

## Runtime configuration

| Variable | Default | Purpose |
|---|---:|---|
| `JARVIS_PROACTIVE_ENABLED` | `true` | Enable/disable the heartbeat |
| `JARVIS_PROACTIVE_INTERVAL_SECONDS` | `900` | Check cadence; clamped to 300–86400 seconds |
| `JARVIS_TIMEZONE` | `America/Sao_Paulo` | Timezone for pattern interpretation |
| `JARVIS_MOBILE_USER_ID` | unset | Authenticated owner identity allowed to receive proactive mobile messages |
| `JARVIS_MOBILE_DEVICE_ID` | unset | Paired mobile device used by the existing dispatch adapter |
| Quiet hours | 22:00–07:00 | Suppress proactive delivery |

On Windows hosts without an installed IANA timezone database, the engine falls back to the host's current local UTC offset. Set `JARVIS_TIMEZONE` and install `tzdata` when DST-aware historical conversion is required.

## Safety and privacy boundaries

- No LLM is called during heartbeat evaluation.
- User history is queried with the authenticated `user_id`; no global history query is used.
- Event signals without a user identity are discarded.
- Delivery uses `NotificationService.communicate_user()` and requires the authenticated `user_id` to match `JARVIS_MOBILE_USER_ID`; the existing presence policy can defer non-urgent notifications.
- No global broadcast, LLM call, tool execution, or external action occurs in the initiative engine.
- Undeliverable proposals remain pending in memory and are retried by the heartbeat or after that same user makes an async request.
- The heartbeat tracks users active in the current process for up to 24 hours.

## Known limitations / next steps

This is a first, conservative vertical slice, not a full Dots-equivalent companion:

1. Active-user registry, pending proposals, and cooldowns are process-local; restart loses them. Durable proposal history and dedupe should be added through an existing user-scoped persistence adapter before multi-instance deployment.
2. Temporal inference uses repeated command text and median time-of-day; it does not yet use calendar events, device routines, project milestones, or learned availability.
3. Help-signal producers must call `AssistantService.on_event(event_type, data)` with a user-scoped payload. Existing producers have not all been wired to emit these event kinds.
4. Delivery currently supports only the configured paired mobile owner (`JARVIS_MOBILE_USER_ID` / `JARVIS_MOBILE_DEVICE_ID`). Other user partitions are not sent to a shared/global channel and remain pending; multi-user push and HUD presentation are not implemented.
5. The user can respond through the normal assistant interface; explicit accept/decline buttons and proposal lifecycle states are not yet implemented.
6. Preparation currently builds a structured objective/evidence package. It does not dispatch a TaskRunner or multi-agent job. Any future execution must go through the existing plan validator, authorization policy, queue, and outcome verification.
7. Relevance scoring is deterministic and rule-based. Thresholds need calibration from observed useful/ignored proposals before widening the initiative types.

## Validation

- `tests/application/test_proactive_initiative_engine.py`: temporal recurrence, insufficient evidence, help signal, quiet hours, cooldown, malformed timestamps.
- `tests/application/test_assistant_proactive_monitor.py`: user-scoped event ingestion, user-scoped pending delivery, monitor lifecycle.
- Runtime/CI verification of AssistantService and API lifecycle integration is still required in an environment with the repository's full dependencies installed.
