# Jarvis Android VPN service and Hev integration

## Implemented

- Pin the upstream HevSocks5Tunnel Android AAR at version 2.20.0 and verify its SHA-256 before Gradle uses it.
- Declare `JarvisVpnService` as a protected Android `VpnService`, with the system VPN bind permission and the required foreground-service type for active VPN apps.
- Require Android 10 (API 29) for the Hev native VPN engine; the app's lower overall minSdk remains supported for aggregate telemetry only.
- Request Android VPN consent from the Presence screen; the user explicitly starts or stops the service.
- Establish a dual-stack TUN interface (IPv4 and IPv6). A packet-preserving AF_UNIX datagram socketpair sits between the Android TUN fd and Hev, allowing one relay loop to inspect headers while forwarding complete packets without a competing TUN reader.
- Preflight the socketpair in both directions before starting Hev; the relay uses nonblocking descriptors, bounded packet queues, and a watchdog failure path that closes the TUN if forwarding stops.
- Run a loopback-only SOCKS5 upstream on `127.0.0.1` on a dynamically allocated local port, requiring per-session random 192-bit username/password credentials shared only with Hev.
- Protect outbound TCP and UDP sockets with `VpnService.protect()` so upstream connections do not recurse into the TUN.
- Forward SOCKS5 TCP CONNECT and UDP ASSOCIATE sessions. Payloads are not logged or persisted.
- Reuse the existing package filter: empty means all apps except Jarvis; a non-empty list becomes Android's allowed-app list. Android requires the TUN to be re-established to change that list.
- Per-flow metadata is a separate, default-off consent toggle (`vpn_flow_sharing_enabled`). When disabled, Hev receives the TUN fd directly and no flow parser/relay is created. Revoking consent during an active capture immediately clears and stops metadata collection; enabling it after VPN startup requires a restart.
- When enabled, parse IPv4/IPv6 TCP/UDP headers in the relay and call Android's VPN-owner-only `ConnectivityManager.getConnectionOwnerUid()` with the original 5-tuple to map flows to UIDs.
- Resolve UID package names and labels through `PackageManager`; publish bounded flow snapshots with protocol, local/remote IP and port, UID/package identity, first/last seen, TX/RX packet counts, and IP packet-byte totals.
- Never store or publish packet payloads, application message bodies, credentials, or TLS contents. Non-initial IP fragments lack transport ports and are not individually attributed.
- Close the native engine, relay socketpair, TUN descriptor, flow collector, SOCKS listener, client sockets, and UDP relays on user stop, service destruction, and `onRevoke()`.

## What this VPN is — and is not

This is an **on-device traffic inspection/forwarding VPN**, not a remote privacy VPN. The local SOCKS5 server creates protected direct sockets over the current Wi-Fi/mobile network. It does not encrypt traffic to a remote gateway, change the public IP, or provide anonymity.

Hev's public JNI statistics are published as `payload.vpn_tunnel_stats` (`tx_packets`, `tx_bytes`, `rx_packets`, `rx_bytes`) for interface-wide totals. The relay additionally publishes up to 25 active/recent per-flow records inside `payload.flows`. Per-flow byte totals are IP packet lengths observed at the TUN boundary; the separate `NetworkStatsManager` collector remains the aggregate per-UID/package accounting source.

UID attribution is attempted once when a flow is first observed. If Android cannot resolve the tuple, the record is retained with `uid=null` and `attribution_status=unresolved` or `denied`; Jarvis does not guess a package. Shared UIDs may map to more than one package name. Flow records are bounded to 1,000 in memory, expire after ten minutes, and each observation includes at most 25 records to stay below the backend payload limit.

## Tailscale coexistence

Android permits only one active `VpnService` owner at a time. Jarvis refuses to establish its TUN while another VPN transport is active. If Tailscale is active, its tunnel remains in control and the existing `NetworkStatsManager` aggregate collection can continue. When the user activates Tailscale over Jarvis, Android revokes Jarvis's VPN ownership and `onRevoke()` tears down the TUN. Android does not silently grant ownership back when Tailscale is disabled; the user must start Jarvis again and approve the system VPN consent if requested.

The public Tailscale Android `IPNReceiver` exposes connect/disconnect control broadcasts, not a flow-telemetry API. The Android build also uses `ipnlocal/web_client_stub.go` (`android` build tag), and its `IPNService` is not exported to other apps; the generic `100.100.100.100/metrics` web-client route is therefore not a supported bridge for Jarvis in the stock Android app. The package being installed does not prove that it owns the active VPN. This change therefore does not label an unknown external VPN as Tailscale and does not claim to read Tailscale's TUN packets.

To collect per-flow metadata through Tailscale, a supported telemetry bridge must be added inside the Tailscale client (maintained fork or upstream API). A normal third-party app cannot read another VPN app's TUN descriptor.

## Safety and rollout

- The service is **manual opt-in** in this phase; AUTO does not start it in the background.
- Devices below Android 10 cannot start the Hev VPN service; the app keeps its existing aggregate network statistics path.
- Starting Jarvis while another VPN is active is refused. The user must explicitly switch VPN ownership through Android's system consent.
- No incomplete tunnel is left active if the Hev worker fails its startup check.
- Per-flow metadata is disabled by default and requires a separate explicit switch in Presence. The backend rejects flow records unless `flow_metadata_opt_in=true`.
- The socketpair is preflighted at runtime, and packet parsing/UID aggregation have unit tests. The Hev-over-AF_UNIX transport and `getConnectionOwnerUid` attribution still require physical-device validation with real TCP, UDP, DNS, IPv4/IPv6, fragmented traffic, mobile/Wi-Fi handover, process death, and revocation before enabling automatic switching.
- Do not enable automatic VPN takeover or claim packet-level collection in production until those device tests pass.

## Upstream references

- HevSocks5Tunnel 2.20.0: https://github.com/heiher/hev-socks5-tunnel/tree/2.20.0
- Android VPN guide: https://developer.android.com/develop/connectivity/vpn
- Tailscale Android client: https://github.com/tailscale/tailscale-android
