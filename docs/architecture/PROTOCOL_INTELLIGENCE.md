# Jarvis Protocol Intelligence

## Purpose

Maintain versioned, reusable descriptions of application communication patterns. The first implementation is a **pattern registry**, not a transparent network proxy and not a protocol replayer.

## Current components

- `BrowserTrafficObserver`: existing opt-in Chromium/CDP observer for HTTP(S) request/response metadata and WebSocket frame metadata. Payload previews are separately opt-in and sanitized.
- `ProtocolPatternRegistry`: append-only JSONL snapshots keyed by package, app version, and operation.
- MCP tools registered by the Android and desktop MCP runtimes:
  - `android_network_flows_snapshot`
  - `protocol_pattern_record_observation`
  - `protocol_pattern_import_android_flows`
  - `protocol_pattern_import_live_android_flows`
  - `protocol_pattern_list`
  - `protocol_pattern_analyze_package`
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

## Capture boundaries and live Android integration

The CDP observer sees Chromium traffic only. Native Android flow inspection is provided by Jarvis's existing `VpnService`/Hev TUN relay while Jarvis owns Android's active VPN slot. A separately authenticated, read-only endpoint on the paired AccessibilityService exposes the current bounded flow snapshot to the Termux MCP runtime. The endpoint reports the capture owner and both consent states, resolves app version metadata only for uniquely attributed package identities, and returns no raw packet bytes.

The live MCP importer stores only DNS question names, cleartext HTTP Host names and visible TLS ClientHello SNI. HTTPS application payloads remain encrypted. It cannot see the private TUN of Tailscale or another VPN provider; when the VPN owner is external, the endpoint explicitly returns `external_vpn_not_owned` and no flows. Do not bypass certificate pinning or extract app secrets. For payload-level protocol study, use an owned test app/server, documented APIs, or an explicitly authorized instrumentation build.

The next increment is controlled test-server fixtures for HTTP/TLS/DNS and version-to-version diff/validation before any adapter is allowed to replay a pattern. No protocol replay engine is implemented yet. `reusable` is a knowledge state, not permission to bypass authentication, app controls, or service terms.

No protocol replay engine is implemented yet. `reusable` is a knowledge state, not permission to bypass authentication, app controls, or service terms.

## Android passive flow metadata import

The Android `VpnService` path already publishes bounded `protocol_observations` with each attributed flow when both flow-sharing and payload-metadata consent are enabled. The Android MCP now exposes `android_network_flows_snapshot(package_filter)` through the authenticated loopback bridge and `protocol_pattern_import_live_android_flows(package)` to read the live snapshot, resolve the installed app version through PackageManager, and import matching observations directly into the Termux-local registry. The lower-level `protocol_pattern_import_android_flows(package, app_version, flows)` remains available for offline/replayed snapshots.

Import rules:

- Only flows with `attribution_status == "resolved"` and exactly one matching `package_names` entry are attributed to the requested package.
- Shared-UID, unresolved, denied, and other-package flows are skipped rather than guessed.
- Only DNS question names, cleartext HTTP Host names, and visible TLS ClientHello SNI are accepted.
- The stored record contains hostname, protocol kind/source, transport, remote IP/port, observation timestamps, package, and supplied app version. It does not store packet bytes, local IP, UID, flow ID, payload, credentials, or message content.
- Imported records remain `observed`; import does not validate a protocol or authorize replay.
- Version comparison supports both HTTP transaction-shape records and Android network-metadata records.

`app_version` must be supplied by the caller. Use `unknown` when the installed package version has not yet been measured; such records should not be used for version-to-version compatibility conclusions.

The importer consumes flow objects already obtained through an authorized observation source. It does not independently fetch the user's Supabase observations. The current API's latest-observation endpoint remains the source of those snapshots and enforces the authenticated user's identity.
