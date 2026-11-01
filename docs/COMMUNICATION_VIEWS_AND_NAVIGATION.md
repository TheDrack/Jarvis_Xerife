# Communication views and navigation

## Goal

The authenticated route `/network-devices` is the Jarvis operational view for registered devices and communication paths. It combines passive inventory with explicitly requested discovery and inspection. It is not a network scanner and does not run a background monitoring bot.

## Views

- **Overview:** registered device counts, heartbeat state, interface count, current API session and latest environment observations.
- **Interfaces:** IPv4 interface addresses, network masks, operational state, speed and MTU reported by the host running the API. Scope distinguishes RFC1918 private, link-local, CGNAT/overlay and public addresses. In cloud deployments this is the cloud host/container, not the user's LAN.
- **Devices:** authenticated inventory with search, type/status filters, sort order, last known IP, network type and capabilities.
- **Cameras:** quick navigation to camera-classified inventory entries. HTTP(S) preview URLs may be displayed only when they contain no embedded credentials. RTSP endpoints are not embedded in browser previews.
- **Discovery:** passive ARP cache, explicit SSDP/ONVIF multicast discovery and explicit mDNS DNS-SD PTR query.
- **Inspection:** one explicitly supplied RFC1918 IPv4 target with bounded TCP port checks and minimal HTTP(S)/RTSP identification.
- **Services:** one explicit MQTT broker CONNECT/CONNACK test on TCP 1883 or 8883, without credentials, publish or subscribe.

## API contract

All routes are registered through the existing authenticated network router and require `get_current_user`:

| Method | Route | Solicitation | Purpose |
|---|---|---:|---|
| GET | `/v1/network/interfaces` | 0 | Read local interface addresses. |
| GET | `/v1/network/discovery` | 0 | Read the existing local ARP/neighbour cache. |
| POST | `/v1/network/device/inspect` | 2 | Inspect one supplied RFC1918 IPv4 host; up to 32 ports, 0.2–3s timeout. |
| POST | `/v1/network/cameras/discover` | 2 | Bounded SSDP and ONVIF multicast discovery; 0.2–5s per protocol. |
| POST | `/v1/network/mdns/discover` | 2 | One bounded mDNS DNS-SD PTR query; 0.2–5s. |
| POST | `/v1/network/mqtt/probe` | 2 | One MQTT handshake to one RFC1918 host, port 1883/8883, 0.2–3s. |

Synchronous network operations use FastAPI's synchronous endpoint execution path rather than blocking the event loop in an `async def` handler. Edge adapter exports are lazy-loaded so a network-only API call does not require optional desktop/audio packages such as PyAutoGUI.

## UI behavior

- Device inventory and environment observations refresh every 15 seconds.
- Interface inventory loads on page entry and manual refresh.
- No active probe runs automatically or during periodic refresh.
- Discovery/inspection buttons initiate only the specific user-requested operation.
- Discovery results remain ephemeral in the browser view; they do not silently register devices or alter the database.
- Unknown heartbeat state remains unknown; absence from inventory is not treated as proof of offline status.
- API data inserted into markup is escaped; device detail JSON is rendered with `textContent` inside an in-page dialog.
- Camera previews accept only HTTP(S) URLs without embedded username/password. The browser is not asked to render RTSP.

## Scope and limitations

- The interface list and ARP cache belong to the machine/container running the API. A cloud deployment cannot infer the user's local network from its own interfaces.
- Active camera and protocol discovery requires the API process to run on the LAN where those multicast probes should be sent. A cloud-hosted API will generally not discover devices on the user's home LAN.
- The dashboard does not proxy or play RTSP streams, authenticate to cameras, read camera credentials, or issue configuration commands.
- A successful TCP connection is not proof that a particular application service is healthy. Protocol identification is reported separately.
- Device inventory status is based on registered heartbeat timestamps, not a live network reachability test.
- Continuous ETW capture, bots, Sentinela, queues and event retention are intentionally outside this delivery.

## Validation

The route contract tests exercise every endpoint through FastAPI TestClient with mocked protocol adapters. They verify parameter forwarding, RFC1918 rejection, supported MQTT ports, and timeout bounds without sending real multicast or TCP probes. Dashboard asset tests verify the navigation views, authenticated API client, explicit action controls, and safe camera preview rules. JavaScript syntax is checked separately with Node.js.
