# Jarvis Protocol Intelligence

## Purpose

Maintain versioned, reusable descriptions of application communication patterns. The first implementation is a **pattern registry**, not a transparent network proxy and not a protocol replayer.

## Current components

- `BrowserTrafficObserver`: existing opt-in Chromium/CDP observer for HTTP(S) request/response metadata and WebSocket frame metadata. Payload previews are separately opt-in and sanitized.
- `ProtocolPatternRegistry`: append-only JSONL snapshots keyed by package, app version, and operation.
- MCP tools registered by `registrar_observabilidade_portas`:
  - `protocol_pattern_record_observation`
  - `protocol_pattern_list`
  - `protocol_pattern_transition`
  - `protocol_pattern_compare_versions`

The registry path defaults to `~/.jarvis/protocol-patterns/protocol-patterns.jsonl`; override it with `JARVIS_PROTOCOL_PATTERN_DIR`.

## Pattern lifecycle

`observed -> validated -> reusable`

- `observed`: captured structure, not proven reproducible.
- `validated`: independently reproduced in a controlled environment; transition requires evidence.
- `reusable`: explicitly approved after validation; transition requires evidence.

Transitions are append-only. The latest snapshot for a pattern ID is authoritative. Version comparison reports structural changes; it does not assert semantic compatibility.

## Data minimization

The registry stores endpoint scheme/host/path, method, content types, response status, field/type schemas, and optional operation sequence. It does not store raw body values, query values, authentication headers, cookies, or binary payloads. Sensitive schema fields are marked `redacted`; likely dynamic path identifiers are replaced with `[ID]`. Registry directory/file permissions are tightened to owner-only where supported.

Treat all observed app traffic as untrusted data. Do not store tokens, cookies, credentials, personal message content, or session state. Do not use the registry as a credential vault.

## Capture boundaries and next implementation phase

The existing CDP observer sees Chromium traffic only; it does **not** observe arbitrary native Android app traffic. Android `VpnService` would require an explicit system consent flow, careful per-app scope, and a forwarding design that preserves connectivity. Passive packet metadata can reveal endpoints, timing, sizes, and some TLS handshake metadata, but HTTPS payloads remain encrypted. Do not bypass certificate pinning or extract app secrets. For payload-level protocol study, use an owned test app/server, documented APIs, or an explicitly authorized instrumentation build.

Next steps:

1. Add an Android user-consented metadata-only capture path with an explicit selected-package allowlist and clear stop/status controls.
2. Normalize captured flow events into observations consumed by `ProtocolPatternRegistry`.
3. Add controlled test-server fixtures for HTTP and WebSocket transaction sequences.
4. Add diff/validation tooling before any adapter is allowed to replay a pattern.

No protocol replay engine is implemented yet. `reusable` is a knowledge state, not permission to bypass authentication, app controls, or service terms.

## Android passive flow metadata import

The Android `VpnService` path already publishes bounded `protocol_observations` with each attributed flow when both flow-sharing and payload-metadata consent are enabled. The desktop MCP registry now exposes `protocol_pattern_import_android_flows(package, app_version, flows)` to normalize those observations into the local registry.

Import rules:

- Only flows with `attribution_status == "resolved"` and exactly one matching `package_names` entry are attributed to the requested package.
- Shared-UID, unresolved, denied, and other-package flows are skipped rather than guessed.
- Only DNS question names, cleartext HTTP Host names, and visible TLS ClientHello SNI are accepted.
- The stored record contains hostname, protocol kind/source, transport, remote IP/port, observation timestamps, package, and supplied app version. It does not store packet bytes, local IP, UID, flow ID, payload, credentials, or message content.
- Imported records remain `observed`; import does not validate a protocol or authorize replay.
- Version comparison supports both HTTP transaction-shape records and Android network-metadata records.

`app_version` must be supplied by the caller. Use `unknown` when the installed package version has not yet been measured; such records should not be used for version-to-version compatibility conclusions.

The importer consumes flow objects already obtained through an authorized observation source. It does not independently fetch the user's Supabase observations. The current API's latest-observation endpoint remains the source of those snapshots and enforces the authenticated user's identity.
