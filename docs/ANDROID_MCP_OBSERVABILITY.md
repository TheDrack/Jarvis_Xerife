# Android MCP metadata-only observability

## Purpose and security boundary

The Android MCP ASGI boundary can optionally emit two JSONL records per HTTP request: `inbound` and `outbound`. It observes only transport metadata and counts body bytes while forwarding ASGI messages unchanged. It does **not** retain request/response bodies, prompts, tool arguments, headers, cookies, bearer tokens, query strings, client addresses, or raw URL paths.

The route field is the framework route template (for example `/v1/sessions/{session_id}`); unresolved routes are recorded as `unmatched`. Each pair shares a locally generated request ID. The records include UTC timestamp, direction, transport, HTTP version, method, route template, byte count, response status (outbound), and elapsed milliseconds.

## Opt-in activation

Disabled by default. Enable only for a controlled diagnostic window by setting these variables in the Android MCP service environment before starting the service:

```sh
JARVIS_ANDROID_MCP_OBSERVABILITY=1
JARVIS_ANDROID_MCP_OBSERVABILITY_LOG="$HOME/.local/state/jarvis-android-mcp/observability.jsonl"
```

The log path is optional; the default is the path shown above. Restarting `jarvis-android-mcp` is required for environment changes to take effect. This change does not alter the installed service environment or restart the running service.

Files are append-only JSONL, created with owner-only permissions (`0600`) in an owner-only directory (`0700`). Rotation is bounded to 1 MiB per file and three backups. Logging is fail-open: an I/O failure must not interrupt MCP requests. The observer is not a packet capture system and cannot decrypt or inspect TLS traffic.

To disable, remove the opt-in variable (or set it to `0`) and restart the MCP service. Treat logs as operational metadata and remove them according to the device's retention policy.

## Tailscale assessment (optional, not required)

Tailscale is useful for private connectivity and access control, not for inspecting application payloads. Its Android split-tunneling setting controls which apps use the tailnet; it does not expose per-app HTTP request bodies to Jarvis. The Android Tailscale app is installed on the inspected device, but the Termux `tailscale` CLI cannot connect to a local `tailscaled` daemon in the current runtime, so CLI-based status/flow collection is unavailable here.

Tailscale Network Flow Logs are a separate optional tailnet feature. They record aggregate connection metadata (such as protocol, addresses/ports where available, packet/byte counters and time windows), not packet contents. They are disabled by default, require Premium or Enterprise, require an authorized tailnet administrator and an API token with `logs:network:read`, retain the latest 30 days, and are not a real-time packet feed. They therefore cannot replace the MCP-boundary observer and are not enabled or wired into this change. If the tailnet later has the required plan and authorization, a separate read-only collector can be considered without changing routing or enabling an exit node.

References:

- [Tailscale Network Flow Logs](https://tailscale.com/docs/features/logging/network-flow-logs)
- [Android app-based split tunneling](https://tailscale.com/docs/features/client/android-app-split-tunneling)
- [Tailscale security model](https://tailscale.com/security)

## Verification

Focused tests:

```sh
pytest -q tests/adapters/edge/test_android_mcp_observability.py --no-cov
```

The tests cover inbound/outbound metadata, body and credential exclusion, route-template handling, fail-open behavior, default-off behavior, owner-only file permissions, bounded rotation, and environment configuration.
