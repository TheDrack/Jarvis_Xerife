"""MCP registration for the read-only host operations toolkit.

Registered additively on the existing Jarvis Desktop MCP server, so the new
tools travel through the same authenticated tunnel. No new port, listener or
credential is introduced.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Sequence

from app.adapters.infrastructure import host_ops

logger = logging.getLogger(__name__)

TOOL_NAMES = (
    "host_fs_list",
    "host_fs_read_text",
    "host_command_profiles",
    "host_command_run",
    "host_command_request_confirmation",
)


def _audit_filesystem_result(event: str, path: str, result: dict[str, Any]) -> dict[str, Any]:
    """Audit filesystem access using a digest, never the caller's raw path."""
    response = dict(result)
    audit_id, audit_logged = host_ops._audit(
        {
            "event": event,
            "status": response.get("status"),
            "path_digest": host_ops._audit_argument_digest([path]),
        }
    )
    response["audit_id"] = audit_id
    response["audit_logged"] = audit_logged
    return response


def register_host_ops_tools(mcp: Any) -> tuple[str, ...]:
    """Register the host operations tools on ``mcp`` and return their names."""

    # Host filesystem and command tools are an explicit local opt-in. The
    # authenticated tunnel is single-user; do not expose this gateway to
    # untrusted or multi-tenant MCP clients.
    enabled = os.environ.get("JARVIS_HOST_OPS_ENABLED", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info("Host operations tools are disabled; set JARVIS_HOST_OPS_ENABLED=1 to opt in")
        return ()

    @mcp.tool(name="host_fs_list")
    def host_fs_list(path: str = ".", depth: int = 1, max_entries: int = 200) -> dict[str, Any]:
        """List directory metadata under an allowed root; never reads file content.

        depth is 0-4 and max_entries 1-500. Symlinks and junctions are reported
        but never followed. Credential-named entries are filtered out.
        """
        try:
            result = host_ops.list_directory(path, depth=depth, max_entries=max_entries)
        except (ValueError, OSError) as exc:
            result = _rejected("list_rejected", exc)
        return _audit_filesystem_result("fs_list", path, result)

    @mcp.tool(name="host_fs_read_text")
    def host_fs_read_text(
        path: str, max_bytes: int = 65_536, max_lines: int = 2_000
    ) -> dict[str, Any]:
        """Read one bounded UTF-8 text file; credentials and private keys are refused.

        max_bytes is 1-262144 and max_lines 1-4000. Token-shaped values are
        redacted before returning. Binary files are refused.
        """
        try:
            result = host_ops.read_text_file(path, max_bytes=max_bytes, max_lines=max_lines)
        except (ValueError, OSError) as exc:
            result = _rejected("read_rejected", exc)
        return _audit_filesystem_result("fs_read", path, result)

    @mcp.tool(name="host_command_profiles")
    def host_command_profiles() -> dict[str, Any]:
        """Describe allowed roots, limits and command profiles (read-only)."""
        return host_ops.describe_profiles()

    @mcp.tool(name="host_command_run")
    def host_command_run(
        profile: str,
        verb: str,
        arguments: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: int = 20,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """Run one structured, allowlisted, non-elevated command (shell=False).

        profile is powershell_readonly, git or inspect_d. arguments is a
        list of separate argv tokens, never a command string. Destructive,
        installation, boot, ACL, credential and privileged operations are
        blocked by policy regardless of confirmation.
        """
        return host_ops.run_host_command(
            profile,
            verb,
            arguments,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            confirm_token=confirm_token,
        )

    @mcp.tool(name="host_command_request_confirmation")
    def host_command_request_confirmation(
        profile: str, verb: str, arguments: Sequence[str] | None = None, cwd: str | None = None
    ) -> dict[str, Any]:
        """Issue a single-use token for a confirmable capability, if one exists.

        No host capability is confirmable today; the call reports
        confirmation_not_applicable. It never enables a blocked operation.
        """
        try:
            return host_ops.request_confirmation(profile, verb, arguments, cwd=cwd)
        except (ValueError, OSError) as exc:
            return _rejected("confirmation_rejected", exc)

    return TOOL_NAMES


def _rejected(status: str, exc: Exception) -> dict[str, Any]:
    return {
        "success": False,
        "status": status,
        "error": f"{type(exc).__name__}: {exc}",
        "read_only": True,
    }
