# ADR-002 — Jarvis Universal Intelligence integration boundary

- **Status:** Accepted for incremental implementation
- **Date:** 2026-11-02

## Context

Jarvis needs a unified intelligence experience across user routine/context, public/global information, local operations and Jarvis self-maintenance. OSIRIS and God's Eye View already solve useful subproblems. Reimplementing their capabilities inside Jarvis core would duplicate mature work and create unnecessary coupling.

## Decision

Jarvis owns the contracts, policy, memory, orchestration and user experience. External systems remain replaceable providers. Their capabilities are integrated through Jarvis application ports and infrastructure adapters, normalized into provenance-preserving domain events, registered in Nexus/Toolbox, and consumed by Universal Intelligence services.

The Jarvis OS host layer supplies platform-specific runtime capabilities but does not own intelligence semantics. Universal Intelligence must remain runnable on the current host and portable to the future Jarvis OS.

## Consequences

- Agents consume capabilities/contracts, never provider SDKs directly.
- OSIRIS/God's Eye View are inspirations and optional external services, not core dependencies.
- Provider-specific UI is not copied wholesale; Jarvis presents one integrated, user-filtered experience.
- Source data licenses/terms are tracked independently from source-code licenses.
- Initial implementation is read-only and public-data-only. No autonomous intervention is authorized by this ADR.
- The existing personal/entity OSINT adapter remains separate from public-event/news intelligence.

## Alternatives rejected

1. Fork OSIRIS and make it the Jarvis intelligence core — rejected due to frontend/runtime coupling and duplicate orchestration.
2. Import God's Eye View wholesale into the core — rejected due to third-party data/asset terms and its own stated exploratory/non-safety-critical status.
3. Build a new parallel API/agent harness — rejected because Nexus, Toolbox, scheduler, memory and existing channels are the integration substrate.
