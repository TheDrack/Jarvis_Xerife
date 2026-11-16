# Jarvis Network Intelligence — Android

## Architectural constraints

- Supported target for this implementation: Android without root.
- Android grants one active `VpnService` per user/profile. Jarvis must not attempt to read another VPN provider's private TUN descriptor.
- Detailed flow attribution is available only while Jarvis owns the active VPN and Android permits `ConnectivityManager.getConnectionOwnerUid()`.
- When an external VPN owns the slot, use only independently available telemetry such as `NetworkStatsManager` and supported provider logs/APIs. Do not claim payload visibility.
- Payload inspection is opt-in, scoped to selected applications/sessions, and must never bypass certificate pinning, application trust configuration, or transport encryption.
- Raw payload bytes must not be persisted or uploaded by the passive metadata pipeline. The future reassembly layer may hold bounded transient bytes in memory only, must clear them after inspection/revocation/flow expiry, and must never emit them to telemetry. Payload evidence requires a separate explicit capture session, retention policy, encryption and audit trail.

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
| Passive protocol metadata parser | Implemented | `PassivePayloadInspector` extracts DNS question names, cleartext HTTP Host and TLS ClientHello SNI from a single supplied transport payload. Unit tests cover normal, malformed and oversized inputs. |
| TUN payload-offset integration | Implemented | `IpPacketParser` exposes validated TCP/UDP payload offsets and lengths for IPv4/IPv6. `TunPacketRelay` passes the packet buffer to the flow collector; the inspector copies only a bounded temporary slice and does not retain raw bytes. |
| Per-flow metadata and consent | Implemented | Separate `vpn_payload_metadata_enabled` opt-in, default-off, requires flow attribution consent and Jarvis VPN ownership. Revocation clears stored per-flow protocol observations immediately. |
| TCP stream reassembly | Implemented | `TcpStreamReassembler` is integrated per flow and direction. It handles in-order data, bounded out-of-order segments, retransmission overlap and 32-bit sequence wrap. It caps each stream at 16 KiB, allows at most 32 active reassembly flows, and wipes transient buffers on successful extraction, revocation, flow expiry, close or overflow. |
| Backend schema and UI | Implemented | Android UI exposes a separate protocol-inspection switch. Publisher sends at most 3 typed observations per flow and caps metadata-enabled snapshots at 15 flows; backend validates type/source/hostname and both opt-ins. |
| TLS diagnostic proxy | Pending | Separate feature, disabled by default, only for user-selected compatible apps and explicit CA installation. |
| PCAPng evidence store | Pending | Separate explicit capture sessions, encryption, quotas, retention and local-first storage. |
| Tailscale gateway | Pending | Preserve Android UID attribution before forwarding; validate routes, loop prevention and failure recovery. |

## Passive metadata parser contract

- Input is one transport payload plus protocol and source/destination ports.
- Maximum inspected payload: 16 KiB.
- Supported passive metadata: UDP DNS and length-prefixed TCP DNS (53/5353), cleartext HTTP Host (80/8000/8080), TLS ClientHello SNI (common TLS ports or visible handshake record).
- Output is a small list of typed metadata observations. It never returns raw bytes, HTTP paths, authorization headers, cookies, request bodies, TLS application data, or credentials.
- DNS compression pointers and message bounds are validated. Hostnames are normalized and length/character bounded.
- TLS ClientHello and HTTP Host parsing now operate on bounded reassembled TCP streams. The first observed payload anchors each direction; bytes preceding that first segment cannot be reconstructed. Each returned stream snapshot is wiped immediately after parsing.
- Encrypted DNS, ECH-protected names, QUIC payload decryption, TLS application data and pinned applications are not decoded by this parser.

## Validation policy

Every behavioral increment must add tests before implementation, pass focused Android unit tests, run the Android debug build and preserve the repository's full Python test/coverage gates. Physical-device validation is required before enabling packet inspection by default. No collection is enabled by this document alone.
