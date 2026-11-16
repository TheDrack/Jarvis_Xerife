# Android dynamic VPN telemetry

## Goal

Use one active Android VPN at a time while selecting the telemetry source dynamically:

- **AUTO** (default): observe the active VPN; prefer a verified Tailscale adapter when available; otherwise use the Jarvis VPN engine only when no external VPN is active.
- **JARVIS**: prefer the Jarvis VPN engine, but never silently replace an already active external VPN.
- **TAILSCALE**: wait for Tailscale; do not start the Jarvis VPN.

The selected preference is stored locally in `jarvis_session.vpn_mode_preference`.

## Implemented in this change

- `VpnStateDetector` observes whether Android currently exposes a VPN transport and whether the Tailscale package (`com.tailscale.ipn`) is installed.
- `VpnModeOrchestrator` is a pure policy component with unit tests for AUTO/JARVIS/TAILSCALE and fallback decisions.
- `BridgeService` registers a default-network callback and publishes a debounced environment observation after network/VPN transitions, in addition to its periodic observation.
- Network observations now report `vpn_provider`, `vpn_collection_mode`, `vpn_mode_preference`, `tailscale_installed`, and `vpn_transport_active`.
- The Presence screen exposes the three local policies.

## Important detection boundary

Android's public `NetworkCapabilities.TRANSPORT_VPN` identifies a VPN transport, not the owning application package. Package installation is not proof that Tailscale owns the currently active tunnel. Therefore the current detector reports an external VPN as `external_unknown`; it does not falsely label every external VPN as Tailscale.

`VpnService.prepare()` reports whether Jarvis has user authorization to establish a VPN. It does not identify the currently active VPN provider. Android grants VPN control to one application at a time and revokes the previous app; the previous service receives `VpnService.onRevoke()`.

## Deliberately not enabled yet

This change does **not** start a Jarvis `VpnService` or claim packet-level inspection. The policy keeps `jarvisPacketEngineReady=false` and `tailscaleAdapterReady=false`, so the actual collector remains the existing opt-in `NetworkStatsManager` aggregate collector.

This is intentional: after `VpnService.Builder.establish()`, the app receives a TUN file descriptor containing IP packets. A production implementation must process and forward those packets through a complete userspace network stack/tun-to-socket engine, protect its own upstream sockets from VPN recursion, preserve TCP/UDP/DNS/IPv4/IPv6 behavior, and shut down safely on `onRevoke()`. Establishing a TUN interface without forwarding would break the phone's connectivity.

Likewise, collecting flows from the existing Tailscale tunnel requires instrumentation inside the Tailscale Android client (or a supported exported telemetry API). A second ordinary Android app cannot read Tailscale's TUN file descriptor. The inspected upstream `IPNReceiver` exposes connect/disconnect broadcast actions for external control, not a flow-telemetry contract; those actions cannot provide packet attribution or counters. See https://github.com/tailscale/tailscale-android/blob/main/android/src/main/java/com/tailscale/ipn/IPNReceiver.java. The upstream client source is available at https://github.com/tailscale/tailscale-android.

## Next implementation phase

1. Select and audit a maintained Android TUN forwarding engine (or integrate the Tailscale Android client source as a maintained fork).
2. Implement a Jarvis `VpnService` with explicit consent, foreground notification, socket protection, and complete packet forwarding.
3. Instrument the Tailscale client to emit flow metadata through a narrow authenticated local IPC interface.
4. Set each adapter's readiness only after integration and runtime tests pass.
5. Test transitions: Tailscale on/off, Jarvis VPN on/off, Wi-Fi/mobile handover, DNS, IPv4/IPv6, TCP/UDP, app attribution, process death, and revocation.

## Privacy boundary

The intended event schema contains connection metadata (UID/package identity, protocol, endpoints, byte counts, and timestamps) only when the corresponding adapter is implemented and enabled. This feature does not decrypt TLS or collect message bodies, prompts, credentials, or HTTPS content.
