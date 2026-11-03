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

## OSIRIS REST adapter 0.6

OsirisRestAdapter consumes only the fixed read-only `/api/earthquakes`, `/api/fires`, `/api/news` and `/api/weather` routes. It uses HTTPS, rejects redirects, streams responses with a 4 MB byte cap, applies a 12-second timeout and limits each normalized route to 100 records. The base origin is supplied explicitly or through `JARVIS_OSIRIS_API_BASE_URL`; no default live deployment is assumed.

Earthquakes preserve USGS event IDs, event times, magnitudes, coordinates and event-page links. Fires preserve NASA FIRMS source attributes and minute-level acquisition timestamps without inventing times for date-only records. OSIRIS /api/fires volcano rows are skipped because they omit the original EONET event ID; the canonical EONET event is ingested through /api/weather instead. News preserves original publisher links, publisher labels and publication times, including ISO and RFC 2822 dates. OSIRIS keyword-derived country-anchor coordinates are not converted into event geolocation.

Weather alerts preserve the underlying NASA EONET, NOAA/NWS or GDACS provider identity, source URL, category, severity, area and expiry metadata. EONET positions are retained only because the upstream route emits Point geometries; GDACS positions come from explicit RSS geo:lat/geo:long values. NOAA/NWS coordinates are omitted because OSIRIS averages polygon vertices into a representative marker without returning the original geometry type. Date fields are retained as source metadata rather than assigned a universal occurred_at/published_at meaning because their semantics differ by provider.

Each route reports independent SourceHealth; one route failure does not discard successful route data. Non-HTTPS publisher links and malformed records are dropped. The feed's risk score and source-side political labels are not treated as verified analysis or corroboration. Cross-post metadata is not converted into multiple independent evidence records.

The adapter is unit-tested against fixtures matching the upstream route shapes. It has not been connected to a configured live OSIRIS deployment; no credentials, production endpoint, Nexus registration, database, scheduler or deployment are changed. Flights, maritime and satellite feeds remain deferred because GEV already supplies moving-entity observation capability; duplicating those feeds requires a separate coverage, privacy and retention justification.

## Intelligence Core 0.2

IntelligenceCore is a pure, provider-neutral application service. It performs no network calls, persistence, scheduling or delivery. For repeated (source_id, event_id) identities, the newest observed_at wins; equal timestamps are resolved by the lexicographically greatest canonical JSON serialization of the complete event. This rule is independent of input order. Candidate correlations use canonical URL equality or exact normalized headlines within the same domain/category and a 24-hour window. Original events and evidence remain separate; a candidate is not corroboration.

## Durable intelligence history 0.7

The first durable-history schema is defined by ADR-004 and migration `20261103100304_intelligence_history.sql`:

- `intelligence_event_snapshots` stores immutable event versions, idempotent by `(source_id, event_id, content_hash)`. The semantic hash excludes volatile observation/collection/ingestion timestamps, so unchanged polling does not create a new version.
- `intelligence_observation_snapshots` stores immutable provider/entity/time observations, idempotent by `(source_id, entity_type, entity_id, observed_at, content_hash)`. Different observation times remain separate; same-time payload variants are retained for deterministic resolution.
- Both tables preserve the full normalized contract in JSONB and expose relational identity/time columns for indexed queries. `observed_at` and database-side `ingested_at` are independent.
- RLS is enabled. `PUBLIC`, `anon`, `authenticated` and `service_role` are revoked before granting only `SELECT` and `INSERT` to the server-side `service_role`; no application UPDATE/DELETE/TRUNCATE permission is granted.
- No retention job or arbitrary TTL is introduced. Retention, archival and partitioning must be defined from measured ingestion volume before recurring high-volume GEV collection.

**Implementation state:** the migration and ADR are present locally but have not been applied to Supabase. The connected project's migration ledger does not match the local migration filename versions, so remote migration/push operations remain blocked pending reconciliation. The persistence port/adapter and PostgreSQL integration tests are the next code increment. The adapter must use the existing server-only `get_supabase_admin_client()` and fail closed; it must never fall back to the public client.

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

1. Add a configured GEV runtime probe and Nexus registration only after a real local checkout/app is available.
2. Implement the append-only Supabase persistence port/adapter, verify idempotent writes against PostgreSQL, and reconcile remote migration history before applying the schema; define retention before recurring high-volume ingestion.
3. Add track continuity as a separate policy service; never infer identity from provider IDs alone.
4. Add evidence/corroboration and contradiction contracts.
5. Compose the Portuguese daily briefing with citations and explicit fact/claim/inference/scenario separation.
6. Connect a real durable scheduler/worker and idempotent delivery.
7. Build a geospatial presentation adapter after comparing MapLibre/Cesium/deck.gl requirements, performance and licenses.
8. Add user preference/direction feedback and Jarvis self-maintenance signals as separate domains.

## Research and licensing notes

- OSIRIS repository declares MIT for code; verify each source/data/asset's own terms before reuse.
- God's Eye View declares MIT for code, but its DATA_SOURCES.md carves out third-party datasets and assets. TeleGeography submarine cable data is CC BY-NC-SA and must not be bundled in a commercial distribution without permission.
- GDELT DOC 2.0 exposes JSON article-list results and a rolling three-month search window; retain original publisher URLs and do not assume GDELT grants redistribution rights to article content.
- NASA EONET v3 returns event metadata, source links and dated GeoJSON geometry; preserve source references and its metadata disclaimer.
- USGS recommends real-time GeoJSON feeds for display applications; retain event-page URLs and magnitude/time/location fields.

## Status semantics

Code exists, unit-tested, CI-tested, connected, authorized, scheduled and end-to-end verified are separate states. Do not mark a source or workflow production-ready without evidence.
