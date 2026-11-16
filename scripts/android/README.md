# Jarvis Android MCP + Secure Tunnel — Termux

This package installs two separate services on Android:

1. **`jarvis-android-mcp`** — a local, read-only MCP server for the phone hosting Termux.
2. **`jarvis-secure-mcp-tunnel`** — the official OpenAI `tunnel-client`, compiled for Android/ARM64, which forwards requests to that local server.

The Android MCP server is not the Desktop MCP server. It does not import desktop UI, Windows, ADB, or desktop host-operation adapters.

## Requirements

- Android ARM64 with Termux installed from a supported source.
- Termux packages: git, golang, clang, make, python, termux-api.
- The companion **Termux:API Android app**, installed from the same source as Termux, for battery and Wi-Fi tools. The MCP server still starts if the companion app or its permissions are unavailable.
- A distinct OpenAI Platform tunnel ID and runtime API key with `Tunnels Read + Use`.

## Install

From the Jarvis repository checkout:

```bash
bash scripts/android/install_secure_mcp_tunnel.sh
```

The installer creates an isolated Python virtual environment under `~/.local/opt/jarvis-android-mcp/venv`, installs the MCP Python SDK, registers both runit services, and builds upstream `openai/tunnel-client` for Android/ARM64 with cgo and Termux clang. The upstream client remains pinned to `v0.0.20` pending a separate compatibility/security validation of newer releases.

The installer does not overwrite an existing non-symlink service path, tunnel profile, runtime key, or existing `tunnel.env`.

## Local Android MCP service

The server binds only to `127.0.0.1:8765` and exposes Streamable HTTP at `/mcp`.

```bash
sv up jarvis-android-mcp
sv status jarvis-android-mcp
curl -fsS http://127.0.0.1:8765/healthz
curl -fsS http://127.0.0.1:8765/readyz
```

Available tools are deliberately read-only and bounded:

| Tool | Output |
|---|---|
| `android_device_status` | Android/Termux runtime, uptime, aggregate storage |
| `android_battery_status` | Allowlisted battery state from Termux:API |
| `android_wifi_status` | Wi-Fi state, signal and link metrics; SSID, BSSID and IP are withheld |

The server does not expose shell execution, arbitrary file reads, location, clipboard, microphone, camera, notifications, or device-control operations. Those capabilities require separate authorization design and tests before being added.

Logs: `~/.local/state/jarvis-android-mcp/log/current`.

## Configure and start the tunnel

```bash
bash scripts/android/configure_secure_mcp_tunnel.sh
sv up jarvis-secure-mcp-tunnel
sv status jarvis-secure-mcp-tunnel
```

Defaults in `~/.config/jarvis/tunnel/tunnel.env`:

- `MCP_LOCAL_HOST=127.0.0.1`
- `MCP_LOCAL_PORT=8765`
- `MCP_SERVER_URL=http://127.0.0.1:8765/mcp`
- `HEALTH_ADDR=127.0.0.1:8767`

The runtime key remains at `~/.config/jarvis/tunnel/runtime-key` with mode `0600`, outside the Git checkout. Never copy it into Git, chat, or logs.

## Validation

```bash
sv status jarvis-android-mcp
curl -fsS http://127.0.0.1:8765/healthz
"$HOME/.local/opt/jarvis-tunnel/bin/tunnel-client" doctor \
  --profile jarvis-android \
  --profile-dir "$HOME/.config/jarvis/tunnel/profiles"
```

A simple GET to `/mcp` is not a valid MCP handshake test. The MCP endpoint expects Streamable HTTP requests (including an MCP `initialize` POST). The `healthz` and `readyz` endpoints prove only that the local ASGI server is live/ready; they do not prove tunnel connectivity or end-to-end ChatGPT tool discovery.

The MCP server intentionally has no independent bearer-token layer because it binds exclusively to loopback and is reached by the separately provisioned Secure MCP Tunnel client. Do not change the bind address to `0.0.0.0` or expose port 8765 to Wi-Fi/LAN.

## Service supervision

The MCP service starts independently. The tunnel service waits for the MCP TCP listener before starting `tunnel-client`, so runit may start both without requiring a fixed startup order. If the MCP server is restarted, runit restarts it independently; the tunnel client reconnect behavior is handled by the upstream client.
