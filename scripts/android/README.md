# Secure MCP Tunnel — Android / Termux

This is the Android host adapter for the same OpenAI Secure MCP Tunnel protocol used by
`scripts/setup_chatgpt_jarvis_tunnel.ps1` on Windows. It builds the upstream
`openai/tunnel-client` source for **Android/ARM64** instead of copying a Linux ELF
binary. The build enables cgo and uses Termux clang so Go can use Android's resolver;
a stock Linux/CGO-disabled binary is not substituted.

## Requirements

- Android ARM64 device with Termux installed from a supported source.
- Termux packages: git, golang, clang, make, python.
- An Android-local MCP server listening on loopback, default `127.0.0.1:8765/mcp`.
- A distinct OpenAI Platform tunnel ID and runtime API key with Tunnels Read + Use.

## Install

From the Jarvis repository checkout:

```bash
bash scripts/android/install_secure_mcp_tunnel.sh
bash scripts/android/configure_secure_mcp_tunnel.sh
```

The installer pins upstream `openai/tunnel-client` at `v0.0.20`, compiles it
on-device for Android/ARM64, and installs a runit service. It does not download
prebuilt release artifacts or silently assume Linux/ARM64 is Android-compatible.

## Service

The service waits up to 180 seconds for the local MCP TCP listener, then executes
the upstream client with the Jarvis Android profile. It binds its health listener
to `127.0.0.1:8767`. The MCP server must also bind to loopback; do not expose it
on `0.0.0.0`.

```bash
sv up jarvis-secure-mcp-tunnel
sv status jarvis-secure-mcp-tunnel
sv down jarvis-secure-mcp-tunnel
tail -f ~/.local/state/jarvis-tunnel/log/current
```

If the service is not yet enabled in the current Termux runit setup, enable it
using the same mechanism used by the existing Jarvis services. The installer
does not replace or rewrite the existing supervisor/boot configuration.

## Configuration

Defaults are in `~/.config/jarvis/tunnel/tunnel.env`:

- `MCP_LOCAL_HOST=127.0.0.1`
- `MCP_LOCAL_PORT=8765`
- `MCP_SERVER_URL=http://127.0.0.1:8765/mcp`
- `HEALTH_ADDR=127.0.0.1:8767`

The runtime key is stored at `~/.config/jarvis/tunnel/runtime-key` with mode
`0600`, outside the Git checkout. Android Termux does not provide Windows DPAPI;
the file is protected by Termux's app-private Linux UID sandbox and filesystem
permissions. Do not sync this file to Git, Dropbox, or logs.

## Important boundary

This package installs and supervises the **tunnel client**, not an Android MCP
server. The Jarvis mobile MCP server must already exist and expose Streamable HTTP
at the configured local URL. The Desktop MCP server is a different host service
and must not be pointed at from the phone unless that is explicitly intended.
