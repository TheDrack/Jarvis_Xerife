# Jarvis network protocol coverage

## Purpose

This matrix distinguishes an existing library, a working transport, device discovery, and actual observability. A protocol is not considered globally monitored merely because the repository contains a client for it.

## Status matrix

| Protocol / layer | Status | Evidence and limitation |
|---|---|---|
| HTTP / HTTPS | Partial; single-host inspector added in this branch | CDP observes attached Chromium contexts. The new inspector performs HTTP HEAD / HTTPS HEAD on one selected RFC1918 IPv4 host. TLS certificate validation remains enabled. This is not process-wide capture. |
| HTTP/2 | Pending | The standard-library HTTP client used by the inspector does not negotiate HTTP/2. |
| HTTP/3 / QUIC | Pending | Requires a dedicated sensor; UDP 443 alone does not prove QUIC. |
| WebSocket / WSS | Partial | CDP observes attached Chromium contexts only. Other processes are not covered. |
| SSE | Pending as a parsed protocol | It may appear as an HTTP response in CDP, but there is no SSE event parser. |
| TCP | Partial; single-host inspector added in this branch | Bounded checks against an explicitly selected RFC1918 IPv4 host. No subnet sweep. |
| UDP | Partial | SSDP and ONVIF use dedicated multicast probes; there is no generic UDP datagram sensor. |
| RTSP | Partial; minimal OPTIONS handshake added in this branch | Ports 554 / 8554 are checked. No SETUP / PLAY or media capture. |
| RTP / RTCP | Pending | Requires observing negotiated media flows and parsing media/control packets. |
| SSDP / UPnP | Integrated in this branch | UDP multicast M-SEARCH, bounded 0.2-5 s collection, metadata parser and deduplication. No automatic access to LOCATION or authentication. |
| ONVIF / WS-Discovery | Integrated in this branch | SOAP multicast probe for NetworkVideoTransmitter and XML parser rejecting DTD / ENTITY. SSDP and ONVIF are separate protocols. |
| MQTT / MQTT-TLS | Partial; minimal CONNECT/CONNACK probe added | `network_probe_mqtt` sends one unauthenticated MQTT 3.1.1 clean-session CONNECT, reads CONNACK, then sends DISCONNECT. TLS on 8883 uses default certificate validation. No credentials, PUBLISH, SUBSCRIBE, or topic payload inspection. |
| DNS | Partial | Reverse DNS lookup exists; no comprehensive DNS telemetry. |
| mDNS / DNS-SD | Partial; PTR discovery added | `network_discover_mdns` sends one bounded PTR query for `_services._dns-sd._udp.local` and parses bounded DNS-SD PTR answers. It does not resolve/fetch advertised endpoints or capture general DNS traffic. |
| ARP | Integrated, passive | Reads the OS neighbor cache. Inactive devices may not appear. |
| ICMP | Pending as observability | No integrated ICMP telemetry has been verified. |
| IPv4 | Partial | Passive ARP and RFC1918 IPv4 host inspection. |
| IPv6 | Pending | NDP neighbor discovery and IPv6 scope validation are not integrated. |
| SSH / RDP / SMB / WinRM | Partial | Known TCP ports can be identified as open; sessions are not authenticated or inspected. |
| ETW / WFP / Npcap | Pending | Windows process/network sensors and packet capture are not integrated. |
| WebRTC | Pending | ICE / STUN / TURN / DTLS / SRTP visibility is not integrated. |
| Named pipes / RPC / IPC | Pending | Requires OS process and IPC instrumentation. |

## New MCP tools

### `network_probe_private_device`

Accepts exactly one explicitly supplied RFC1918 IPv4 address. The default TCP port set is bounded; a custom list is limited to 32 ports. Concurrency is capped at 16 and timeout at 0.2-3 seconds. It performs TCP connect checks and minimal HTTP HEAD / RTSP OPTIONS handshakes. It does not scan a CIDR, execute commands, try credentials, or open video streams. HTTPS uses the default certificate validation context.

An open port is evidence only that a TCP socket accepted a connection. HTTP, HTTPS, or RTSP is confirmed only when its minimal protocol response is compatible.

### `network_probe_mqtt`

Accepts one RFC1918 IPv4 host and port 1883 or 8883. Sends one MQTT 3.1.1 CONNECT with a random client ID and clean-session flag, reads CONNACK, then sends DISCONNECT. No username/password, PUBLISH, SUBSCRIBE, or topic access. Port 8883 uses TLS with standard certificate verification. This creates a brief broker connection and should be invoked only on an explicitly selected host.

### `network_discover_mdns`

Sends one mDNS DNS-SD PTR query to `224.0.0.251:5353`, with a bounded response window. It parses PTR service announcements only and does not resolve or fetch endpoints.

### `network_discover_camera_protocols`

Explicitly sends one SSDP M-SEARCH and one ONVIF WS-Discovery SOAP Probe to the local-link multicast group `239.255.255.250`, ports 1900 and 3702 respectively. Collection timeout is limited to 0.2-5 seconds per protocol. It parses response metadata only; it does not fetch device descriptions, authenticate, or open media streams. It requires the Jarvis MCP process to be on the same local link as the devices.

## Next integrations

1. Validate SSDP and ONVIF discovery against actual cameras, including explicit interface selection and multiple network adapters.
2. Validate mDNS discovery on a real local link and add bounded DNS observability without storing sensitive payloads.
3. Add MQTT connection-state and session metrics without recording payloads or credentials by default.
4. Integrate ETW / WFP and optional Npcap for Windows process and packet visibility.
5. Treat IPv6 / NDP, QUIC / HTTP/3, WebRTC, RTP / RTCP and IPC as independent modules.

## Operational limits

- No production network scan was run. MQTT CONNECT/CONNACK/DISCONNECT was verified against a temporary local broker bound to the workstation interface. An mDNS PTR query was sent on the local link but no device responded; parser behavior is covered by synthetic DNS packets.
- Passive ARP discovery remains separate from active host inspection.
- Do not assume the user's LAN is `/24`; the TCP inspector requires an explicit target IP.
- Multicast discovery is an active local-link operation and is invoked only by its dedicated MCP tool.
- Encrypted traffic is not treated as readable without authorized endpoint instrumentation.
- The CDP observer is not a host-wide packet sensor.
