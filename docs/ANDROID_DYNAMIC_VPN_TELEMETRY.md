# Android dynamic VPN telemetry

## Goal

Use one active Android VPN at a time while selecting the telemetry source dynamically:

- **AUTO** (default): preserve an external VPN and block Jarvis startup while it is active; continue aggregate per-UID statistics. When no external VPN is active, Jarvis VPN startup remains manual.
- **JARVIS**: allow the user to explicitly request Jarvis VPN startup. If another VPN is active, Android controls the provider switch and may revoke it after the system's consent flow.
- **TAILSCALE**: block Jarvis VPN startup and wait for an external VPN. Android's public transport API does not identify the owning package.

The selected preference is stored locally in `jarvis_session.vpn_mode_preference`.

## Dynamic handoff behavior

- When Jarvis owns the VPN slot and another VPN is activated, Android arbitrates the transition and revokes Jarvis through `VpnService.onRevoke()`. Jarvis closes its TUN, Hev worker, SOCKS proxy, and flow collector; it does not attempt to keep a competing tunnel alive.
- While the Presence/Bridge foreground service is running, its `ConnectivityManager` callback detects the external VPN and keeps publishing environment observations. Collection switches to `external_vpn_stats`; app-level aggregate counters remain available through `NetworkStatsManager`.
- When the external VPN disappears, Jarvis posts a notification offering to resume its own VPN. Tapping it opens `MainActivity`, which calls `VpnService.prepare()` and starts Jarvis only after any Android consent screen is completed.
- The handoff state is persisted locally to avoid repeated notifications. Choosing TAILSCALE suppresses the offer to restart Jarvis.
- The handoff monitor currently depends on the user-started Presence/Bridge service remaining alive. If Presence is stopped or Android terminates it, automatic detection/notification is unavailable until Presence runs again.

This is intentionally not a silent VPN takeover. Android controls the exclusive VPN slot and may require a foreground user interaction to authorize Jarvis again. The Tailscale telemetry adapter is not ready, so the stock Tailscale client continues to use aggregate `NetworkStatsManager` counters rather than exposing its TUN flows to Jarvis.

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

This is a **local forwarding/inspection VPN**, not a remote encrypted privacy VPN. Traffic exits directly through the current Wi-Fi/mobile network. Hev's interface-wide counters are published in `vpn_tunnel_stats`; the existing `NetworkStatsManager` remains the source of per-UID/package aggregate counters. With the separate `vpn_flow_sharing_enabled` opt-in, the Jarvis-owned VPN parses IPv4/IPv6 TCP/UDP headers at the TUN boundary and calls `ConnectivityManager.getConnectionOwnerUid()` to associate supported 5-tuples with Android UIDs. Packet payloads are forwarded to Hev but are not included in telemetry or persisted by Jarvis. This path is unavailable while another VPN owns the tunnel and still requires physical-device validation; keep the toggle default-off. The in-memory flow cache is bounded and expires after ten minutes. The API's five-minute `expires_at` is currently a freshness marker, not proof that historical database rows are deleted; durable retention/erasure remains a separate policy gap.

The service is user-authorized. AUTO never silently replaces an external VPN; the OS performs the handoff, and returning to Jarvis is initiated by a notification tap so Android can present consent if needed. Physical-device tests are still required for real connectivity, DNS, IPv4/IPv6, TCP/UDP, handover, process death, and revocation. See [ANDROID_JARVIS_VPNSERVICE.md](ANDROID_JARVIS_VPNSERVICE.md).

## Tailscale integration boundary

Android's public `NetworkCapabilities.TRANSPORT_VPN` identifies an active VPN transport, not the owning application. The Tailscale package being installed is not proof that it owns the active tunnel. The current detector therefore reports an external VPN as `external_unknown`; it does not falsely label every external VPN as Tailscale. In that state, `external_vpn_stats` keeps per-UID aggregate counters available while packet-level flow inspection remains unavailable.

The public Tailscale Android `IPNReceiver` exposes connect/disconnect broadcasts for external control, not a flow-telemetry contract. A second ordinary Android app cannot read Tailscale's TUN descriptor. Flow collection through Tailscale requires instrumentation inside its Android client or a supported exported API. See https://github.com/tailscale/tailscale-android/blob/main/android/src/main/java/com/tailscale/ipn/IPNReceiver.java.

## Privacy boundary

The intended event schema contains connection metadata (UID/package identity, protocol, endpoints, byte counts, and timestamps) only when the corresponding adapter is implemented and enabled. This feature does not decrypt TLS or collect message bodies, prompts, credentials, or HTTPS content.
