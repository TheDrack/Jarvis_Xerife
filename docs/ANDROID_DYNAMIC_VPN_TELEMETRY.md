# Android dynamic VPN telemetry

## Goal

Use one active Android VPN at a time while selecting the telemetry source dynamically:

- **AUTO** (default): preserve an external VPN and block Jarvis startup while it is active; continue aggregate per-UID statistics. When no external VPN is active, Jarvis VPN startup remains manual.
- **JARVIS**: allow the user to explicitly request Jarvis VPN startup. If another VPN is active, Android controls the provider switch and may revoke it after the system's consent flow.
- **TAILSCALE**: block Jarvis VPN startup and wait for an external VPN. Android's public transport API does not identify the owning package.

The selected preference is stored locally in `jarvis_session.vpn_mode_preference`.

## Current implementation boundary

The policy reports and observes VPN state; it does not yet automatically start Jarvis when an external VPN turns off. The Presence screen's start/stop controls remain manual. Selecting TAILSCALE explicitly stops an active Jarvis VPN so the user can activate Tailscale; selecting JARVIS permits a manual Android-mediated provider switch. The Tailscale telemetry adapter is not ready, so the stock Tailscale client continues to use the existing aggregate `NetworkStatsManager` collector.

## Implemented in this change

- `VpnStateDetector` observes whether Android currently exposes a VPN transport and whether the Tailscale package (`com.tailscale.ipn`) is installed.
- `VpnModeOrchestrator` is a pure policy component with unit tests for AUTO/JARVIS/TAILSCALE and fallback decisions.
- `BridgeService` registers a default-network callback and publishes a debounced environment observation after network/VPN transitions, in addition to its periodic observation.
- Network observations now report `vpn_provider`, `vpn_collection_mode`, `vpn_mode_preference`, `tailscale_installed`, and `vpn_transport_active`.
- The Presence screen exposes the three local policies.

## Important detection boundary

Android's public `NetworkCapabilities.TRANSPORT_VPN` identifies a VPN transport, not the owning application package. Package installation is not proof that Tailscale owns the currently active tunnel. Therefore the current detector reports an external VPN as `external_unknown`; it does not falsely label every external VPN as Tailscale. In this case the collection mode remains `external_vpn_stats`: per-UID aggregate counters can continue through `NetworkStatsManager`, while packet-level flow inspection is unavailable.

`VpnService.prepare()` reports whether Jarvis has user authorization to establish a VPN. It does not identify the currently active VPN provider. Android grants VPN control to one application at a time and revokes the previous app; the previous service receives `VpnService.onRevoke()`.

## Jarvis VPN implementation status

The Android app now includes an explicitly user-started `JarvisVpnService` backed by HevSocks5Tunnel 2.20.0 and a loopback-only SOCKS5 proxy. The native AAR is pinned by SHA-256 and downloaded during Gradle build. TCP CONNECT and UDP ASSOCIATE are forwarded using outbound sockets protected with `VpnService.protect()`. The service closes the TUN descriptor and native worker on stop or `onRevoke()`.

The service reuses the package filter: an empty filter routes all apps except Jarvis; a populated filter routes only the named packages. Changing this list requires re-establishing the VPN.

This is a **local forwarding/inspection VPN**, not a remote encrypted privacy VPN. Traffic exits directly through the current Wi-Fi/mobile network. Hev's interface-wide counters are published in `vpn_tunnel_stats`; the existing `NetworkStatsManager` remains the source of per-UID/package aggregate counters. This integration does not yet publish per-flow records or correlate each SOCKS flow to its originating Android UID.

The service is manual opt-in in this phase. AUTO does not start or replace a VPN in the background. Physical-device tests are still required for real connectivity, DNS, IPv4/IPv6, TCP/UDP, handover, process death, and revocation before automatic switching is enabled. See [ANDROID_JARVIS_VPNSERVICE.md](ANDROID_JARVIS_VPNSERVICE.md).

## Tailscale integration boundary

Android's public `NetworkCapabilities.TRANSPORT_VPN` identifies an active VPN transport, not the owning application. The Tailscale package being installed is not proof that it owns the active tunnel. The current detector therefore reports an external VPN as `external_unknown`; it does not falsely label every external VPN as Tailscale. In that state, `external_vpn_stats` keeps per-UID aggregate counters available while packet-level flow inspection remains unavailable.

The public Tailscale Android `IPNReceiver` exposes connect/disconnect broadcasts for external control, not a flow-telemetry contract. A second ordinary Android app cannot read Tailscale's TUN descriptor. Flow collection through Tailscale requires instrumentation inside its Android client or a supported exported API. See https://github.com/tailscale/tailscale-android/blob/main/android/src/main/java/com/tailscale/ipn/IPNReceiver.java.

## Privacy boundary

The intended event schema contains connection metadata (UID/package identity, protocol, endpoints, byte counts, and timestamps) only when the corresponding adapter is implemented and enabled. This feature does not decrypt TLS or collect message bodies, prompts, credentials, or HTTPS content.
