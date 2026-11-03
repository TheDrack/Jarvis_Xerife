# Jarvis Universal Intelligence — Architecture 0.1

## Purpose

Universal Intelligence is the synthesis layer of Jarvis. It combines user-directed context, public/global information, local operational state and Jarvis engineering telemetry into a traceable view. It is not a replacement for Nexus, the universal Toolbox, the Jarvis OS host foundation, or existing provider projects.

## Integration rule: reuse, isolate, normalize

External projects such as OSIRIS (https://github.com/Pendia/OSIRIS-Dashboard-OSINT) and God's Eye View (https://github.com/bilawalsidhu/gods-eye-view) are reference implementations and optional capability providers. Jarvis owns its contracts, policy, memory, orchestration and user experience. External capabilities are consumed through Jarvis ports/adapters; do not fork their runtime into Jarvis core or modify Jarvis core to match their internals.

- OSIRIS is a reference for source aggregation, domain layers, progressive loading and evidence-linked multi-agent forecast UX.
- God's Eye View is a reference for 3D geospatial rendering, source-layer isolation, viewport-aware loading and attribution.
- Provider implementations remain replaceable without changing agents, memory, Nexus or Jarvis OS.

## Logical layers

1. Inputs: user-directed preferences/routines; public news and event feeds; Jarvis repo/CI/service state; host/device observations.
2. Source adapters: bounded, read-only connectors. Agents do not import provider SDKs or issue HTTP calls directly.
3. Normalized knowledge: immutable events and evidence references with source ID, publisher, URL, publication/collection times, terms, location and domain.
4. Intelligence services: deduplication, entity/event resolution, corroboration, contradiction detection, classification and briefing composition.
5. Agent analysis: task-scoped agents produce sourced claims, uncertainty and dissent; external content is untrusted data, never executable instruction.
6. Presentation: briefing feed, alert inbox, searchable history and geospatial view. The map is a view over normalized events, not a separate source of truth.
7. Delivery: existing Jarvis channels and OS surfaces; schedules require a real scheduler/worker, not metadata alone.

## Initial read-only source slice (0.1)

PublicIntelligenceAdapter provides GDELT DOC article search, NASA EONET open events and the USGS all-day earthquake GeoJSON feed. It emits the common IntelligenceEvent/IntelligenceEvidence contract. Requests are bounded, time-limited and HTTPS-only for source links; article bodies and raw provider payloads are not persisted. Source failure is explicit; absence of returned events is not evidence that no event exists.

This source slice is now followed by a deterministic application-level synthesis core. It removes repeated source/event identities, selects the newest observation, and resolves equal-timestamp payload conflicts with a canonical full-event JSON tie-breaker. Durable history, semantic entity resolution, briefing composition, scheduling, delivery and map rendering remain separate increments.

## Entity observations 0.3

IntelligenceObservation is separate from IntelligenceEvent. It represents a provider's time-stamped observation of an entity or mapped asset (for example, an aircraft, vessel, satellite or camera). It requires a provider identity, entity type, stable entity ID, observation timestamp and at least one provenance record; position is optional and structured attributes are bounded scalar values.

The batch/report contract carries observations and event records independently, with separate input/unique/duplicate counts. The core deduplicates only an exact provider/entity/time snapshot identity. Different timestamps remain separate history points; different providers and entities are never merged. Equal-time conflicting payloads use a canonical full-observation JSON tie-breaker, independent of input order. This is not entity resolution or track continuity: those require a separate policy and evidence.

## God's Eye View MCP adapter 0.4

GodsEyeMcpAdapter is an optional Edge adapter. It starts the configured local GEV MCP stdio process, discovers the live tools/list catalog, and invokes only the explicit query allowlist aircraft_in_area, vessels_in_area and satellites_overhead when the current definition carries annotations.readOnlyHint=true. It does not call show_in_gods_eye_view, panel_request, or other action/app-only tools.

The adapter requires an explicit geographic bounding box no larger than 10 degrees per side, caps each result at 100 rows, applies per-call timeouts, and accepts only a loopback GEV API origin. The MCP entrypoint is configured through JARVIS_GEV_MCP_ENTRYPOINT or an explicit constructor argument; the process command is fixed to node, not user-supplied. The Python MCP SDK is imported lazily and is an Edge dependency (requirements/edge.txt), so core/headless imports remain independent.

Returned aircraft, vessel and satellite rows become IntelligenceObservation records with deterministic IDs, timestamps, bounded scalar attributes and source provenance. Missing identities/timestamps are dropped; missing satellite coordinates remain None. Partial tool failures are reflected in SourceHealth without discarding successful rows.

This adapter is unit-tested with an injected fake MCP session. It has not been verified against a configured live God's Eye View checkout or running app. No endpoint, credentials, database, scheduler, production service or deployment is configured by this change. GEV's MIT code license does not grant rights to underlying data/assets; provider attribution and dataset terms remain applicable.

## Optional OSIRIS REST event adapter

- Adapter: \`app/adapters/infrastructure/intelligence/osiris_rest_adapter.py\`; class: \`OsirisRestAdapter\`.
- Opt-in HTTPS integration through \`JARVIS_OSIRIS_API_BASE_URL\` or an explicit constructor origin.
- Calls only \`/api/earthquakes\`, \`/api/fires\` and \`/api/news\`; no user-controlled route, query, redirect or remote URL fetcher.
- Each route is independently bounded to 100 records, a 4 MB streamed response and a 12-second timeout by default; source health preserves partial failures.
- News country-anchor coordinates are intentionally not treated as event coordinates. News items require an HTTPS original publisher link and a valid ISO/RFC 2822 publication timestamp.
- Unit tests use upstream-shaped fixtures and an injected HTTPX MockTransport. No live OSIRIS deployment is configured or verified.

## Intelligence Core 0.2

IntelligenceCore is a pure, provider-neutral application service. It performs no network calls, persistence, scheduling or delivery. For repeated (source_id, event_id) identities, the newest observed_at wins; equal timestamps are resolved by the lexicographically greatest canonical JSON serialization of the complete event. This rule is independent of input order. Candidate correlations use canonical URL equality or exact normalized headlines within the same domain/category and a 24-hour window. Original events and evidence remain separate; a candidate is not corroboration.

## Data and trust model

- Preserve publisher/source URL, publication time and collection time separately.
- A source record is an observation or claim, not an established fact.
- Corroboration must link independent evidence; repeated syndication is not independent confirmation.
- Track source terms/license metadata. Code licenses do not license third-party datasets or assets.
- Do not ingest private data, identify/track named people, perform facial recognition, or turn public cameras into individual surveillance.
- Never expose provider credentials to the browser, model prompts, logs or source control.
- Geospatial and forecast outputs are informational, not navigation, emergency-response or safety-critical guidance.

## Jarvis OS compatibility

Domain contracts and application services remain OS-neutral. Host-specific scheduling, storage, notification and rendering are adapters selected by Nexus. The current Windows environment is a development host, not a permanent architectural dependency. The same intelligence contracts must run under the future Jarvis OS host profile.

## Next increments

1. Add the per-route OSIRIS REST adapter with upstream-derived fixtures.
2. Add a configured GEV runtime probe and Nexus registration only after a real local checkout/app is available.
3. Add durable observation history and retention policies.
4. Add track continuity as a separate policy service; never infer identity from provider IDs alone.
5. Add evidence/corroboration and contradiction contracts.
6. Compose the Portuguese daily briefing with citations and explicit fact/claim/inference/scenario separation.
7. Connect a real durable scheduler/worker and idempotent delivery.
8. Build a geospatial presentation adapter after comparing MapLibre/Cesium/deck.gl requirements, performance and licenses.
9. Add user preference/direction feedback and Jarvis self-maintenance signals as separate domains.

## Research and licensing notes

- OSIRIS repository declares MIT for code; verify each source/data/asset's own terms before reuse.
- God's Eye View declares MIT for code, but its DATA_SOURCES.md carves out third-party datasets and assets. TeleGeography submarine cable data is CC BY-NC-SA and must not be bundled in a commercial distribution without permission.
- GDELT DOC 2.0 exposes JSON article-list results and a rolling three-month search window; retain original publisher URLs and do not assume GDELT grants redistribution rights to article content.
- NASA EONET v3 returns event metadata, source links and dated GeoJSON geometry; preserve source references and its metadata disclaimer.
- USGS recommends real-time GeoJSON feeds for display applications; retain event-page URLs and magnitude/time/location fields.

## Status semantics

Code exists, unit-tested, CI-tested, connected, authorized, scheduled and end-to-end verified are separate states. Do not mark a source or workflow production-ready without evidence.
