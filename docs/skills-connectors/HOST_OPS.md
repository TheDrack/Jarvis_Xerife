# Host operations over the authenticated MCP tunnel

Read-only host tooling for agents that reach the local MCP server through the Secure MCP Tunnel (or through Tailscale Serve / stdio). It replaces ad-hoc UI automation for the routine engineering loop: inspect a directory, read a text file, run one allowlisted command.

**Non-goal:** this is not a general remote shell. It never writes files, installs software, changes the boot configuration, edits ACLs, touches credentials or elevates privileges.

## Enablement and trust boundary

Host operations tools are **disabled by default**. The local MCP server registers them only when its process environment contains `JARVIS_HOST_OPS_ENABLED=1` (also accepts `true`, `yes` or `on`). Set this variable in the server's own supervisor/task environment, then restart the MCP server.

This is an owner-controlled feature opt-in, not per-call authorization. The Secure MCP Tunnel is user-scoped and must not be shared with untrusted or multi-tenant clients. Every caller authenticated to this single-user gateway can invoke enabled tools. Do not enable host operations on a gateway shared with other users.

## Tools

| Tool | Purpose | Limits |
|---|---|---|
| `host_fs_list` | Directory metadata (`path`, `depth`, `max_entries`) | depth 0–4, 1–500 entries, symlinks/junctions reported but not followed, credential-named entries filtered |
| `host_fs_read_text` | Read one UTF-8 text file (`path`, `max_bytes`, `max_lines`) | ≤ 256 KiB, ≤ 4 000 lines, binary refused, recognized private-key formats refused, token-shaped values redacted |
| `host_command_profiles` | Effective roots, limits and profile verbs | read-only, no side effects |
| `host_command_run` | Run one structured command (`profile`, `verb`, `arguments`, `cwd`, `timeout_seconds`) | argv list only, `shell=False`, ≤ 60 s; stdout/stderr are drained concurrently and retained within byte caps before redaction/truncation (16 000/4 000 output characters maximum) |
| `host_command_request_confirmation` | Issue a single-use token for a confirmable capability | no capability is confirmable today; always returns `confirmation_not_applicable` |

When enabled, all five tools are registered on the existing `Jarvis Desktop` FastMCP server; no new port, listener or credential is introduced.

## Allowed roots

Default on Windows: the repository root and `D:\`. On other platforms: the repository root only. Override explicitly:

```powershell
$env:JARVIS_HOST_OPS_ROOTS = "D:\\"
```

The repository root is always appended. UNC/device paths and mapped network drives are rejected before any resolution. Symlink and NTFS reparse-point components are rejected before `Path.resolve()`, so resolution never follows a caller-controlled link. `..` segments, `~` paths and control characters are rejected.

## Command profiles

### `powershell_readonly`

Verbs: `Get-ChildItem`, `Get-Item`, `Test-Path`, `Resolve-Path`, `Get-FileHash`, `Get-Process`, `Get-Service`, `Get-NetTCPConnection`, `Get-NetAdapter`, `Get-PSDrive`, `Get-ComputerInfo`, `Get-Date`.

Each verb has its own parameter allowlist. **Positional or parameter values are never concatenated into a shell line** — the process is launched with `powershell.exe -NoLogo -NoProfile -NonInteractive -Command <validated single command>`, every value is single-quoted after rejecting quotes/metacharacters, and the process runs non-elevated with an allowlisted environment (no `JARVIS_*`, `OPENAI_*`, `AWS_*`, `GIT_*`).

```json
{"profile": "powershell_readonly", "verb": "Get-ChildItem",
 "arguments": ["-Path", "D:/", "-Depth", "1", "-Directory"]}
```

### `git`

The Git profile rejects working directories outside the repository root. Test execution is deliberately left to GitHub Actions: running arbitrary test code on the host would violate the read-only boundary. PowerShell path parameters accept filesystem paths only; provider-qualified paths such as `Registry::`, `Env:`, `Cert:` and `Variable:` are rejected. Listing filters credential directories such as `.ssh`, `.aws`, `.kube` and `.docker`; direct reads inside those directories are blocked.

The `show` and `diff` verbs require `--stat` or `--name-only`. Raw patch/content output is not exposed through this profile. Secret redaction covers known provider-prefixed environment variable names, common API tokens, AWS key identifiers, key-data fields and database connection URLs. This is best-effort pattern matching, not a guarantee that arbitrary secrets are detected.

Read-only subcommands: `status`, `log`, `diff`, `show`, `rev-parse`, `ls-files`, `branch`, `describe`. `-C`, `--git-dir`, `--work-tree`, `--exec-path`, `--upload-pack` and `-c` are rejected; `-c core.fsmonitor=false` and `-c core.untrackedCache=false` override repository settings that could execute helper programs; system/global Git configuration and optional index writes are disabled. `--no-pager` is always added and `GIT_TERMINAL_PROMPT=0` prevents interactive credential prompts.

```json
{"profile": "git", "verb": "log", "arguments": ["-n", "5", "--oneline"]}
```

### `inspect_d`

`Get-ChildItem` and `Get-Item` only; every path must resolve under `D:\`. Intended for inventorying the second Windows installation without PowerShell string building.

## Hard blocks

Rejected by pattern before any spawn, regardless of arguments or tokens:

- file/dir mutation (`Remove-Item`, `del`, `rd`, `Set-Content`, `Out-File`, `New-Item`, `Move-Item`, `Copy-Item`, `Rename-Item`);
- disk/boot (`format`, `diskpart`, `mkfs`, `fdisk`, `sgdisk`, `bcdedit`, `bootrec`, `efibootmgr`, `grub-install`);
- ACL/ownership (`icacls`, `takeown`, `cacls`);
- registry (`reg add/delete/import`);
- services/processes (`Stop-Service`, `Start-Service`, `Restart-Service`, `Stop-Process`, `Start-Process`), scheduled tasks;
- execution policy, dynamic code (`Invoke-Expression`, `Invoke-Command`, `Invoke-WebRequest`), package installation (`pip install`, `apt install`, `winget`, `choco`, `Install-Package`);
- account/privilege (`net user`, `New-LocalUser`, `Add-LocalGroupMember`, `sudo`, `runas`, `Start-Job`).

A blocked call returns `status: "operation_blocked"` and is audited. It is never executed, even with a confirmation token.

## Confirmation gate (and its current limitation)

`host_command_request_confirmation` issues an HMAC token bound to `(profile, verb, arguments, cwd)`, valid 120 s and single-use. The gate is intentionally **inert**: `_CONFIRMABLE_PROFILES` is empty, so no host capability can be unlocked today. Enabling a capability requires a policy review, an entry in that set, tests proving destructive operations stay blocked, and a new release — it is not a configuration switch.

This is the safe fallback for the requirement that destructive operations need a separate explicit confirmation: the mechanism is auditable and tested, while destructive execution itself remains impossible rather than merely gated.

## Audit

Every command attempt and every filesystem list/read attempt (executed, blocked, rejected, timeout, launch failure) appends one JSON line to `JARVIS_HOST_OPS_AUDIT_LOG` (default `~/.local/share/jarvis/host_ops_audit.jsonl`). Filesystem paths are represented by a keyed digest; raw caller paths are not persisted. Child-process output is drained concurrently and capped in memory before redaction:

```json
{"ts":"2026-11-10T12:00:00+00:00","audit_id":"…","event":"executed","profile":"git",
 "verb":"status","arguments":["--short"],"digest":"…","cwd":"…","exit_code":0,
 "elapsed_ms":120,"truncated":false,"confirmed":false,"elevated":false}
```

Command arguments are never persisted; only a one-way argument digest and count are logged. Audit files are created with owner-only permissions on POSIX. Output content, environment and secrets are never written. If the log cannot be written the call still returns, with `audit_logged: false`.

## Activation on the local server

1. Deploy the branch to the machine that runs the MCP server and restart it (the tools are registered at import time):

```powershell
# same command the scheduled task uses
python -m app.adapters.edge.jarvis_desktop_mcp
```

2. Confirm registration through the tunnel or locally:

```powershell
# MCP initialize + tools/list over the local loopback endpoint
python scripts/check_mcp_tools.py   # or any MCP client: look for the five host_* tools
```

3. Smoke test, in order, from the agent:

```json
{"tool": "host_command_profiles"}
{"tool": "host_fs_list", "path": "D:/", "depth": 1, "max_entries": 50}
{"tool": "host_fs_read_text", "path": "README.md", "max_bytes": 4096}
{"tool": "host_command_run", "profile": "git", "verb": "status", "arguments": ["--short"]}
```

4. Negative checks (must fail closed):

```json
{"tool": "host_fs_read_text", "path": ".env"}
{"tool": "host_fs_list", "path": "../.."}
{"tool": "host_command_run", "profile": "powershell_readonly", "verb": "Remove-Item", "arguments": ["-Path", "C:/x"]}
{"tool": "host_command_run", "profile": "powershell_readonly", "verb": "Get-Item", "arguments": ["-Path", "C:/Windows"]}
```

## Verification evidence

- `tests/adapters/infrastructure/test_host_ops.py` — path traversal, symlink escape, secret filename/content blocking, redaction, byte/line limits, per-profile argv validation, hard blocks, timeout/truncation, audit, token binding/replay.
- `tests/adapters/infrastructure/test_host_ops_mcp_tools.py` — registration surface and simulated tool calls.

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/adapters/infrastructure/test_host_ops.py tests/adapters/infrastructure/test_host_ops_mcp_tools.py -q --basetemp=.tmp/pytest-basetemp
```

## Limits to disclose to users

- Secret-name and content filters are defense-in-depth heuristics. The denylist covers common cloud, database, SSH, PGP, PuTTY, OpenVPN, Kubernetes and Terraform credential stores, but is not exhaustive. Never treat tool output as proven secret-free; avoid reading configuration or deployment files unless needed.

- Read-only: no file writes, no installs, no boot/ACL/credential changes, no elevation.
- `inspect_d` and `powershell_readonly` require Windows PowerShell; on Linux the profile returns `command_rejected`.
- The tools observe metadata and text; they do not interpret binaries, archives or Office documents.
- Reading a file still exposes its (redacted) content to the model conversation: treat it as data leaving the host, and prefer narrow `max_bytes`.
- A legitimately sensitive operation must be performed by the user through the normal desktop/terminal, not through these tools.
