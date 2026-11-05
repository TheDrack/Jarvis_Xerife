# ADR-003 — OSIRIS and God's Eye View provider integration

- **Status:** Accepted for incremental implementation
- **Date:** 2026-11-02
- **Depends on:** ADR-002; Universal Intelligence Core 0.2

## Context

Jarvis Universal Intelligence must synthesize information exposed by OSIRIS and God's Eye View without importing either application's runtime or treating their visualizations as a source of truth.

The projects expose materially different integration surfaces:

- **OSIRIS** is a Next.js application. Its repository documents read-oriented feed routes such as `/api/flights`, `/api/earthquakes`, `/api/cctv`, `/api/news`, `/api/fires`, `/api/maritime`, `/api/gdelt`, `/api/satellites` and `/api/weather`. It also documents an OI API with SSE and an MCP endpoint. Feed response shapes are domain-specific, and some feeds aggregate third-party providers.
- **God's Eye View (GEV)** is a local-first Vite/Cesium application. Its portable query tools are exposed through an MCP server over STDIO; the MCP process reads data from a running GEV application. The documented local HTTP MCP route is loopback-restricted. Query tools include earthquakes, active fires, aircraft, vessels, satellites, CCTV, weather, infrastructure and other map layers.

These are not interchangeable event feeds. Aircraft, vessels, satellites and cameras are time-varying entities or infrastructure observations, not necessarily discrete events. The current `IntelligenceEvent` contract alone is insufficient to represent them without semantic distortion.

## Decision

1. Jarvis remains the owner of canonical contracts, authorization, memory, synthesis, orchestration and user experience.
2. OSIRIS and GEV are optional, replaceable providers. Provider-specific SDKs, response shapes and runtime code stay outside the domain and application core.
3. Integrations begin read-only and use bounded requests, explicit timeouts, per-provider health, provenance and source attribution.
4. GEV is integrated through its documented MCP query surface (prefer STDIO for a local installation; HTTP MCP only when the loopback trust boundary is preserved). Discover tool schemas at session start. Invoke only explicitly allowlisted query tools that declare read-only behavior. Do not invoke action tools such as `show_in_gods_eye_view` or app-only `panel_request` as intelligence ingestion.
5. OSIRIS is integrated through explicitly configured HTTPS base URLs and a per-route allowlist. Normalize each selected feed separately; never accept arbitrary URLs from tool arguments. Do not call RECON scanner, WHOIS, DNS, sanctions, wallet-tracing, sweep or other active/security-sensitive routes as part of passive intelligence ingestion.
6. The `/api/oi` forecasting/SSE interface is a later analytical provider, not the first raw-data ingestion surface. Its model execution, costs, key handling and forecast semantics require a separate adapter and policy.
7. Extend the domain model before ingestion of moving entities: introduce immutable, provenance-preserving observations distinct from `IntelligenceEvent`. An observation must identify provider, entity type and stable entity ID; retain observation time, optional geospatial point and bounded structured attributes; and link source evidence. Extend batches/reports without changing the meaning of existing event counts.
8. The IntelligenceCore may deduplicate observations by `(source_id, entity_type, entity_id, observed_at)` only when the provider's identity and snapshot semantics justify it. It must not merge different entities or infer continuity between snapshots without a separate track-resolution policy.
9. The GEV globe and OSIRIS map remain presentation surfaces. Jarvis's normalized history is the source of truth; map links/views are optional presentation metadata.

## Initial read-only allowlists

### GEV MCP query tools

Initial candidates, subject to runtime `tools/list` schema and `readOnlyHint` verification:

- `get_earthquakes`
- `get_active_fires`
- `aircraft_in_area`
- `vessels_in_area`
- `satellites_overhead`
- `find_cctv_cameras`
- `get_cyclones`
- `get_fire_perimeters`
- `get_weather`
- `get_wind`
- `find_infrastructure`

The caller must provide bounded areas/limits where required. A truncated response is never interpreted as complete coverage. Query tools that require an API key report unavailable when that key is absent; do not silently substitute an empty dataset.

**Implemented in the adapter:** `aircraft_in_area`, `vessels_in_area`, `satellites_overhead`, `find_cctv_cameras`, `find_infrastructure`, `find_military_installations`. Every call still requires a runtime `readOnlyHint` and a required `area`/`location` property. Static mapped assets use the query instant as `observed_at`; the remaining candidates stay unimplemented until a captured schema and a dedicated parser exist.

### OSIRIS REST feed routes

Initial candidates, subject to endpoint-level response contract tests:

- `GET /api/earthquakes`
- `GET /api/fires`
- `GET /api/flights`
- `GET /api/maritime`
- `GET /api/satellites`
- `GET /api/weather`
- `GET /api/news`
- `GET /api/cctv` (only bounded region/viewport queries; camera feed URLs are metadata, not content to proxy)

Each endpoint must have a dedicated parser and a fixture based on its actual repository implementation. A non-2xx response, provider-level error field, malformed payload, stale cache marker or partial source failure must be represented explicitly in source health. A successful HTTP status with an empty array is not proof of complete coverage.

**Implemented in the adapter:** `earthquakes`, `fires`, `news`, `weather` and `gdelt` as events; `flights`, `maritime`, `satellites` and `cctv` as bounded observations. `flights` preserves the provider's `alt` field verbatim and labels it as such because the route does not state a unit; `cctv` ingests directory metadata only and never proxies or probes a stream.

## Security and data governance

- Require HTTPS for remote OSIRIS origins; permit loopback HTTP only for an explicitly local deployment.
- Validate configured hostnames and reject redirects to unapproved hosts; do not build a general-purpose URL fetcher.
- Keep API keys server-side. Never place provider credentials in event attributes, evidence, prompts, logs, browser responses or source control.
- Treat all provider payloads as untrusted data and never execute embedded instructions.
- Do not ingest private data, identify/track named people, perform facial recognition, or infer identity from camera/vehicle data.
- Preserve provider attribution and terms at the individual dataset/layer level. GEV's MIT code license does not relicense its bundled/live datasets or assets. In particular, its documented TeleGeography submarine-cable dataset is CC BY-NC-SA 3.0 and must not enter a commercial distribution without separate permission or removal.
- Do not use forecasts or geospatial outputs for navigation, emergency response or other safety-critical decisions.

## Delivery sequence

1. **Domain prerequisite:** add observation contracts and deterministic unit tests while preserving existing event behavior.
2. **GEV adapter:** implement an optional MCP STDIO client adapter with an explicit read-only query allowlist, dynamic schema discovery, bounded area/limit arguments, timeout/cancellation and source health. Test with a fake MCP server; run an opt-in local acceptance test only when a GEV instance is configured.
3. **OSIRIS adapter:** implement per-route HTTPS parsers for the first selected feeds (earthquakes/fires/flights/maritime), each with captured fixtures and malformed/stale/partial-response tests.
4. **Synthesis:** process event and observation collections independently; add explicit entity-track resolution only after identity/temporal semantics are specified.
5. **Persistence and briefing:** store immutable evidence-linked records, then compose a Portuguese briefing that separates observation, claim, inference and scenario.
6. **Presentation:** expose normalized data to Jarvis UI and optionally create GEV views or OSIRIS deep links; never make either map the canonical database.

## Acceptance criteria

- No provider dependency imported by domain/application code.
- Provider base URLs and process commands are configuration, not user-controlled request arguments.
- Every invoked GEV tool is verified as a query/read-only tool from the live MCP catalog.
- Every OSIRIS route is fixed/allowlisted and covered by a fixture derived from the corresponding upstream route implementation.
- Tests prove provenance preservation, stable IDs, UTC timestamps, bounded result counts, truncation/staleness visibility, timeout/cancellation and partial-source failure behavior.
- Existing IntelligenceCore event behavior and its test suite remain unchanged.
- No production endpoint, credential, deployment or database is changed by the initial integration PR.
- Runtime integration is marked unverified until a configured GEV/OSIRIS instance completes a read-only end-to-end probe.

## Repository evidence reviewed

- Jarvis: `docs/architecture/jarvis-universal-intelligence.md`, `docs/architecture/ADR-002-jarvis-universal-intelligence.md`, `app/domain/intelligence/contracts.py`, `app/application/services/intelligence_core.py`, `app/application/ports/intelligence_source.py`, `requirements/edge.txt`.
- OSIRIS: public README and implementations of `src/app/api/earthquakes/route.ts`, `src/app/api/flights/route.ts`, and `src/app/api/cctv/route.ts`.
- GEV: public README, `docs/TOOLS.md`, `server/mcp/stdio.js`, `server/mcp/server.js`, `src/tools/index.js`, `src/tools/queries/hazards.js`, and `SECURITY.md`.

## References

- https://github.com/Pendia/OSIRIS-Dashboard-OSINT
- https://github.com/bilawalsidhu/gods-eye-view
- https://github.com/bilawalsidhu/gods-eye-view/blob/main/docs/TOOLS.md
- https://github.com/bilawalsidhu/gods-eye-view/blob/main/DATA_SOURCES.md
