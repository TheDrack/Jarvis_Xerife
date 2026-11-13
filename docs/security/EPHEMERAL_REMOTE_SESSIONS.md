# Ephemeral remote sessions for Jarvis host operations

## Scope

This is a second authorization layer for the opt-in host-operations MCP tools. It does not replace Tailscale identity, transport security, Windows account permissions, the host filesystem allowlist, or the structured command allowlists.

The first increment exposes two fixed profiles:

- `observer`: bounded directory listing, bounded/redacted text reads, and command-profile metadata.
- `developer`: observer capabilities plus the existing read-only Git and D: inspection command profiles.

Neither profile grants filesystem writes, arbitrary shell execution, process termination, privilege elevation, service administration, credential access, or unrestricted desktop input. There is no `administrator` or `full-control` profile in this increment.

## Local setup

Host operations remain disabled unless the Jarvis Desktop MCP server process has:

```powershell
$env:JARVIS_HOST_OPS_ENABLED = "1"
```

Set that variable in the environment used to start the MCP server (for example, the scheduled-task launcher); setting it in an unrelated terminal does not change an already-running process. Do not enable the tools on a multi-tenant or untrusted MCP endpoint.

From the repository root on the Jarvis PC, issue a session locally:

```powershell
python -m app.adapters.infrastructure.session_authorization create --profile developer --ttl-minutes 30
```

The CLI prints a random, high-entropy pairing code once. Share it only with the intended authenticated ChatGPT session, then call the MCP tool `host_session_authenticate` with that code. The code is consumed on first successful authentication and is not stored in plaintext. The gateway stores only its SHA-256 digest until pairing, then clears the digest.

**Important:** the pairing code is a bearer credential. A value entered into a chat or tool call may be retained in that service's conversation/tool history. It is single-use and short-lived, but this does not make disclosure risk zero. Do not reuse it. If it may have been exposed, revoke the session immediately.

## Session controls

- MCP `host_session_status`: returns non-secret session metadata.
- MCP `host_session_revoke`: revokes the active session.
- Local CLI: `python -m app.adapters.infrastructure.session_authorization status`
- Local CLI: `python -m app.adapters.infrastructure.session_authorization revoke`

The default state file is under `%LOCALAPPDATA%\Jarvis\session_authorization.json` on Windows, or `~/.local/state/jarvis/session_authorization.json` on POSIX. POSIX permissions are restricted to the owner (directory 0700, file 0600). On Windows, the file inherits the current user's LocalAppData ACL; deployments with custom ACL requirements should provision that directory accordingly.

Sessions last 5–120 minutes (default 30). Only one unexpired session may exist at a time. Five failed pairing attempts lock the code. Every host operation re-reads the state and checks expiry, revocation, profile integrity, and the exact required capability. Revocation from the local CLI is observed by the running MCP server on the next operation.

The authenticated session is held in MCP-process memory. Restarting the MCP process requires a new pairing; a consumed code cannot be reused.

## Audit and transport

Host-operation audit records include the session ID, profile, capability or command profile, and operation metadata. They never include the pairing code. Keep the existing Tailscale-only ingress and transport security enabled. This implementation does not add a challenge-response protocol or make an insecure transport safe.

## Remaining integration boundary

This increment gates the opt-in host filesystem and structured host-command tools, the bounded shell navigator, and the restricted Desktop MCP PowerShell command tool. It is not yet a global authorization middleware for every desktop/Android input or browser-navigation tool registered by the Desktop MCP server. Those tools must not be described as covered by this session gateway until their own capability checks are composed into the server's request dispatch path. Starting the tunnel task requires a separate `host.tunnel.control` capability, which neither profile grants.
