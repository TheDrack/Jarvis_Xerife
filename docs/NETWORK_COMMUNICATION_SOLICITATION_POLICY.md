# Network and communication solicitation policy

## Purpose

Apply a common acquisition/consumption model to every communication surface without forcing every sensor or agent to operate continuously. Acquisition may be broad where technically and legally authorized; consumers must subscribe to the minimum event classes needed for their task.

The solicitation level describes how the capability obtains data. It does not grant permission to access a device, bypass authentication, scan an arbitrary network, retain personal data indefinitely, or modify remote systems.

## Solicitation levels

| Level | Name | Contract |
|---|---|---|
| 0 | Passive | Read telemetry or caches already maintained by the OS/application. No new network request. |
| 1 | On demand | Perform a bounded lookup/inspection only when a user or authorized agent requests it. |
| 2 | Active bounded | Send a protocol-specific probe with explicit target/scope, timeout, rate and packet/response limits. Metadata-only unless a separate capability explicitly authorizes more. |
| 3 | Continuous sensor | A dedicated worker owns persistent/rotating capture, health checks, retention and loss accounting. Consumers use filtered subscriptions or queries. |
| 4 | Intervention | Change network/device configuration, send application commands, disconnect sessions, block traffic or otherwise alter state. Separate authorization and audit trail required. |

## Capability matrix

| Communication surface | Default level | Acquisition/consumer contract | Current implementation status |
|---|---:|---|---|
| Windows TCP/IP ETW | 1 | Broad event-class mask during a bounded capture; preserve raw event fields; normalize endpoint/PID/process-start key; return results to the caller. | Implemented and live-tested in `windows_etw_network_adapter.py`; no persistent history yet. |
| Windows TCP/IP ETW for Sentinela | 3 | Dedicated worker, circular/rotating sessions, durable queue/store, retention, health and loss metrics; publish filtered summaries/events. | Planned; not enabled by this on-demand adapter. |
| OS interface inventory | 0 | Read local interface addresses and networks. | Existing `network_discovery_adapter.network_interfaces`. |
| OS ARP/neighbour cache | 0 | Read existing cache only; no active probing. | Existing `network_discovery_adapter.discover_devices`. |
| Reverse DNS for a private host | 1 | Resolve one explicit private address; bounded lookup. | Existing `network_discovery_adapter.inspect_private_address`. |
| Browser CDP / Portas observer | 0–1 | Observe attached browser contexts; payload previews remain opt-in/redacted. Browser scope is not host-wide network visibility. | Existing `portas_*` adapters. |
| SSDP / ONVIF WS-Discovery | 2 | Explicit local discovery request; bounded multicast scope/TTL/timeout; metadata only. | Protocol adapters exist in the separate network-observability PR; do not treat them as merged into this branch. |
| mDNS / DNS-SD | 2 | Bounded multicast service discovery; parse records without connecting to advertised services. | Protocol adapter exists in the separate network-observability PR; do not treat it as merged into this branch. |
| MQTT protocol probe | 2 | Explicit broker/port; minimal CONNECT/CONNACK/DISCONNECT; no credentials, publish or subscribe by default. | Protocol adapter exists in the separate network-observability PR; do not treat it as merged into this branch. |
| TCP / HTTP(S) / RTSP inspection | 2 | One explicit private host and bounded port list; handshake/metadata inspection only. | Protocol adapter exists in the separate network-observability PR; do not treat it as merged into this branch. |
| WebSocket mobile/desktop channel | 1 by default; 3 only for a dedicated worker | Request/response messaging is on demand; presence/heartbeat may be a separate low-volume continuous channel. Keep command and telemetry streams distinct. | Existing mobile/desktop integration; inspect actual runtime connectivity before claiming availability. |
| Telegram or external messaging | 1 | Send only after destination and action are explicit; inbound polling/webhooks are separate from outbound commands. | Existing adapter; connection and permissions are runtime-dependent. |
| Firewall, router, camera or endpoint configuration | 4 | No implicit mutation from discovery or telemetry. Require explicit authorization, preview/diff, audit and post-action verification. | Separate capability and approval flow required. |

## Separation of responsibilities

1. **Sensor** acquires source data and emits structured events. It should not decide whether an event is malicious.
2. **Normalizer** preserves source fields and adds derived fields without deleting the raw representation.
3. **Transport/queue** buffers events and applies backpressure. It must expose dropped-event and retry counters.
4. **Consumer** requests or subscribes to only the event classes it needs. Jarvis can request a one-shot diagnostic; Sentinela can own continuous monitoring.
5. **Policy engine** evaluates findings and produces recommendations or alerts.
6. **Intervention executor** performs state-changing actions only through an explicit approval policy and auditable tool.

## Data and resource controls

- Every active capture has an explicit source/provider, duration, target/scope, event mask, and maximum output size.
- Every continuous sensor has a rotation/retention policy, health state, queue limits, backpressure behavior, and measurable loss counters.
- Unknown loss counters must be represented as unknown/null, never as zero.
- Preserve timestamps, source identity, event IDs, raw fields and provenance.
- Avoid storing packet payloads or secrets by default. If a future protocol-specific feature needs payloads, it must be a separate opt-in capability with its own data handling policy.
- Continuous acquisition does not imply continuous LLM inference. Prefer deterministic filtering, aggregation and rule evaluation before asking an LLM to interpret a subset.
- Discovery never authorizes connection to an advertised service, authentication attempts, credential collection, or configuration changes.

## Next implementation sequence

1. Complete and merge the bounded ETW sensor after its PR and required CI checks are reviewed.
2. Define the event envelope and queue contract shared by ETW, protocol discovery, browser observer and mobile presence.
3. Add a durable, bounded event store/queue with retention and explicit loss accounting.
4. Implement Sentinela as a separate consumer with rules, severity, deduplication and escalation policy.
5. Add continuous sensors only where the source supports safe session ownership, rotation and recovery.
6. Add intervention tools last, with explicit approvals and rollback/verification.
