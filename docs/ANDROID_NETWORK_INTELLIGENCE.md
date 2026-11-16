# Jarvis Network Intelligence — Android

## Architectural constraints

- Supported target for this implementation: Android without root.
- Android grants one active `VpnService` per user/profile. Jarvis must not attempt to read another VPN provider's private TUN descriptor.
- Detailed flow attribution is available only while Jarvis owns the active VPN and Android permits `ConnectivityManager.getConnectionOwnerUid()`.
- When an external VPN owns the slot, use only independently available telemetry such as `NetworkStatsManager` and supported provider logs/APIs. Do not claim payload visibility.
- Payload inspection is opt-in, scoped to selected applications/sessions, and must never bypass certificate pinning, application trust configuration, or transport encryption.
- Raw payload bytes must not be persisted or uploaded by the passive metadata pipeline. Payload evidence requires a separate explicit capture session, retention policy, encryption and audit trail.

## Target pipeline

1. Android `VpnService` / Hev TUN relay.
2. Flow attribution: UID, package identity, five-tuple, timestamps and counters.
3. Passive protocol metadata: DNS question names, cleartext HTTP Host and TLS ClientHello SNI where visible.
4. Optional, explicit TLS diagnostic proxy for compatible applications that accept a user-installed diagnostic CA. No pinning bypass.
5. Optional PCAPng evidence capture with explicit session authorization and bounded encrypted storage.
6. Correlation and transport through the Jarvis gateway; Tailscale is a transport/telemetry complement, not a second simultaneous Android VPN.

## Implementation progress

| Step | State | Evidence / boundary |
|---|---|---|
| Architecture and platform constraints | Complete | User approved Android unrooted + payload-inspection target on 2026-11-16. |
| Passive protocol metadata parser | In progress | `PassivePayloadInspector` extracts DNS question names, cleartext HTTP Host and TLS ClientHello SNI from a single supplied transport payload. Unit tests specify normal and malformed cases. Not yet connected to the TUN relay. |
| TUN payload-offset integration | Pending | Extend the IP parser to expose a validated transport payload range without copying or retaining the full packet. |
| Per-flow metadata and consent | Pending | Add a separate default-off preference for protocol metadata; revocation must clear metadata immediately. |
| TCP stream reassembly | Pending | Bounded, sequence-aware reassembly is required for split/out-of-order TLS ClientHello and HTTP headers. Until then, the passive parser only handles complete messages present in one segment. |
| Backend schema and UI | Pending | Validate and publish only bounded metadata; expose explicit consent in Android UI. |
| TLS diagnostic proxy | Pending | Separate feature, disabled by default, only for user-selected compatible apps and explicit CA installation. |
| PCAPng evidence store | Pending | Separate explicit capture sessions, encryption, quotas, retention and local-first storage. |
| Tailscale gateway | Pending | Preserve Android UID attribution before forwarding; validate routes, loop prevention and failure recovery. |

## Passive metadata parser contract

- Input is one transport payload plus protocol and source/destination ports.
- Maximum inspected payload: 16 KiB.
- Supported in the first parser increment: UDP DNS (53/5353), cleartext HTTP Host (80/8000/8080), TLS ClientHello SNI (TCP).
- Output is a small list of typed metadata observations. It never returns raw bytes, HTTP paths, authorization headers, cookies, request bodies, TLS application data, or credentials.
- DNS compression pointers and message bounds are validated. Hostnames are normalized and length/character bounded.
- TLS parsing requires a complete ClientHello record in the supplied segment. No TCP stream reassembly is implied.
- Encrypted DNS, ECH-protected names, QUIC payload decryption, TLS application data and pinned applications are not decoded by this parser.

## Validation policy

Every behavioral increment must add tests before implementation, pass focused Android unit tests, run the Android debug build and preserve the repository's full Python test/coverage gates. Physical-device validation is required before enabling packet inspection by default. No collection is enabled by this document alone.
