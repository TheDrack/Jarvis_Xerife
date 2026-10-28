---
name: jarvis-context-memory
description: Mandatory cross-provider startup, context reconciliation, and memory consolidation protocol for every AI agent using Jarvis.
---

# Jarvis Context & Memory

At the beginning of each new session or task, read `docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md` and `docs/skills-connectors/CATALOG.md` when repository context is available.

## Mandatory workflow

1. Discover live tools/connectors and permissions; their schemas are authoritative.
2. Load the small core rules, relevant project memory, task state, and unresolved blockers from the configured Jarvis backend.
3. Compare saved context with live state and evidence before relying on it.
4. Work under Jarvis operating rules: investigate, preserve existing behavior, implement additively, test without disabling valid tests, verify, and report evidence precisely.
5. At milestones and handoff, propose a compact memory update. Deduplicate, retire stale active notes, preserve important audit history, label uncertainty, and never store secrets.
6. Persist using the actual authorized backend and confirm the write. If no writable backend exists, return the proposed update marked NOT PERSISTED.
7. On the next session, verify that the saved update can be retrieved.

## Provider limitation

Do not claim to modify a provider's native memory unless a supported provider interface confirmed the write. Jarvis shared memory is the portable source of truth; native memory is an optional provider-specific mirror.

See `docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md` for record fields, conflict rules, status envelope, and acceptance tests.
