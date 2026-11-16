# Jarvis Android VPN service and Hev integration

## Implemented

- Pin the upstream HevSocks5Tunnel Android AAR at version 2.20.0 and verify its SHA-256 before Gradle uses it.
- Declare `JarvisVpnService` as a protected Android `VpnService`, with the system VPN bind permission and the required foreground-service type for active VPN apps.
- Require Android 10 (API 29) for the Hev native VPN engine; the app's lower overall minSdk remains supported for aggregate telemetry only.
- Request Android VPN consent from the Presence screen; the user explicitly starts or stops the service.
- Establish a dual-stack TUN interface (IPv4 and IPv6) and hand its file descriptor to the Hev JNI worker.
- Run a loopback-only SOCKS5 upstream on `127.0.0.1:10808`, requiring per-session random 192-bit username/password credentials shared only with Hev.
- Protect outbound TCP and UDP sockets with `VpnService.protect()` so upstream connections do not recurse into the TUN.
- Forward SOCKS5 TCP CONNECT and UDP ASSOCIATE sessions. Payloads are not logged or persisted.
- Reuse the existing package filter: empty means all apps except Jarvis; a non-empty list becomes Android's allowed-app list. Android requires the TUN to be re-established to change that list.
- Close the native engine, TUN descriptor, SOCKS listener, client sockets, and UDP relays on user stop, service destruction, and `onRevoke()`.

## What this VPN is — and is not

This is an **on-device traffic inspection/forwarding VPN**, not a remote privacy VPN. The local SOCKS5 server creates protected direct sockets over the current Wi-Fi/mobile network. It does not encrypt traffic to a remote gateway, change the public IP, or provide anonymity.

Hev's public JNI statistics are now published as `payload.vpn_tunnel_stats` (`tx_packets`, `tx_bytes`, `rx_packets`, `rx_bytes`). They are interface-wide counters: they do not identify the originating Android package or expose per-flow metadata by themselves. The existing `NetworkStatsManager` collector remains the source of per-UID/package aggregate RX/TX counters.

The SOCKS5 layer sees destination addresses and ports as it forwards connections, but this first integration does not yet publish a per-flow event schema or map each forwarded flow back to the originating package. That requires additional TUN/UID correlation work and device-level verification before claiming per-app flow attribution.

## Tailscale coexistence

Android permits only one active `VpnService` owner at a time. Jarvis refuses to establish its TUN while another VPN transport is active. If Tailscale is active, its tunnel remains in control and the existing `NetworkStatsManager` aggregate collection can continue.

The public Tailscale Android `IPNReceiver` exposes connect/disconnect control broadcasts, not a flow-telemetry API. The package being installed does not prove that it owns the active VPN. This change therefore does not label an unknown external VPN as Tailscale and does not claim to read Tailscale's TUN packets.

To collect per-flow metadata through Tailscale, a supported telemetry bridge must be added inside the Tailscale client (maintained fork or upstream API). A normal third-party app cannot read another VPN app's TUN descriptor.

## Safety and rollout

- The service is **manual opt-in** in this phase; AUTO does not start it in the background.
- Devices below Android 10 cannot start the Hev VPN service; the app keeps its existing aggregate network statistics path.
- Starting Jarvis while another VPN is active is refused. The user must explicitly switch VPN ownership through Android's system consent.
- No incomplete tunnel is left active if the Hev worker fails its startup check.
- Runtime network-transition, DNS, IPv4/IPv6, TCP/UDP, mobile/Wi-Fi handover, process-death, and revocation tests still need to be run on a physical Android device before enabling automatic switching.
- Do not enable automatic VPN takeover or claim packet-level collection in production until those device tests pass.

## Upstream references

- HevSocks5Tunnel 2.20.0: https://github.com/heiher/hev-socks5-tunnel/tree/2.20.0
- Android VPN guide: https://developer.android.com/develop/connectivity/vpn
- Tailscale Android client: https://github.com/tailscale/tailscale-android
