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
from app.adapters.infrastructure.session_authorization import (
    SESSION_GATEWAY,
    SessionAuthorizationError,
)

logger = logging.getLogger(__name__)

TOOL_NAMES = (
    "host_fs_list",
    "host_fs_read_text",
    "host_command_profiles",
    "host_command_run",
    "host_command_request_confirmation",
    "host_session_authenticate",
    "host_session_status",
    "host_session_revoke",
)


def _audit_result(event: str, result: dict[str, Any], **details: Any) -> dict[str, Any]:
    """Return a host-operations result with one structured audit record."""
    response = dict(result)
    audit_id, audit_logged = host_ops._audit(
        {"event": event, "status": response.get("status"), **details}
    )
    response["audit_id"] = audit_id
    response["audit_logged"] = audit_logged
    return response


def _audit_filesystem_result(
    event: str, path: str, result: dict[str, Any], **details: Any
) -> dict[str, Any]:
    """Audit filesystem access using a digest, never the caller's raw path."""
    try:
        path_digest = host_ops._audit_argument_digest([path])
    except (UnicodeError, TypeError, ValueError, OverflowError):
        path_digest = "unavailable"
    return _audit_result(event, result, path_digest=path_digest, **details)


def register_host_ops_tools(mcp: Any) -> tuple[str, ...]:
    """Register the host operations tools on ``mcp`` and return their names."""

    # Host filesystem and command tools are an explicit local opt-in. The
    # authenticated tunnel is single-user; do not expose this gateway to
    # untrusted or multi-tenant MCP clients.
    enabled = os.environ.get("JARVIS_HOST_OPS_ENABLED", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info("Host operations tools are disabled; set JARVIS_HOST_OPS_ENABLED=1 to opt in")
        return ()

    @mcp.tool(name="host_session_authenticate")
    def host_session_authenticate(pairing_code: str) -> dict[str, Any]:
        """Consume the one-time code issued locally by the Jarvis session CLI."""
        try:
            result = SESSION_GATEWAY.authenticate(pairing_code)
            return {"success": True, "status": "authenticated", **result}
        except SessionAuthorizationError as exc:
            logger.warning("Remote session pairing rejected: %s", str(exc))
            return {"success": False, "status": "authentication_denied", "error": str(exc)}

    @mcp.tool(name="host_session_status")
    def host_session_status() -> dict[str, Any]:
        """Return non-secret metadata about the current local session."""
        return SESSION_GATEWAY.status()

    @mcp.tool(name="host_session_revoke")
    def host_session_revoke() -> dict[str, Any]:
        """Revoke the active session immediately; safe to call without a session."""
        return SESSION_GATEWAY.revoke()

    def _authorize(capability: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            return SESSION_GATEWAY.require(capability), None
        except SessionAuthorizationError as exc:
            denied = _audit_result(
                "session_authorization_denied",
                {"success": False, "status": "session_authorization_denied", "error": str(exc)},
                capability=capability,
            )
            return None, denied

    @mcp.tool(name="host_fs_list")
    def host_fs_list(path: str = ".", depth: int = 1, max_entries: int = 200) -> dict[str, Any]:
        """List directory metadata under an allowed root; never reads file content.

        depth is 0-4 and max_entries 1-500. Symlinks and junctions are reported
        but never followed. Credential-named entries are filtered out.
        """
        authorization, denied = _authorize("host.fs.list")
        if denied:
            return denied
        try:
            result = host_ops.list_directory(path, depth=depth, max_entries=max_entries)
        except (ValueError, OSError) as exc:
            result = _rejected("list_rejected", exc)
        return _audit_filesystem_result(
            "fs_list", path, result,
            session_id=authorization["session_id"], profile=authorization["profile"],
        )

    @mcp.tool(name="host_fs_read_text")
    def host_fs_read_text(
        path: str, max_bytes: int = 65_536, max_lines: int = 2_000
    ) -> dict[str, Any]:
        """Read one bounded UTF-8 text file; credentials and private keys are refused.

        max_bytes is 1-262144 and max_lines 1-4000. Token-shaped values are
        redacted before returning. Binary files are refused.
        """
        authorization, denied = _authorize("host.fs.read")
        if denied:
            return denied
        try:
            result = host_ops.read_text_file(path, max_bytes=max_bytes, max_lines=max_lines)
        except (ValueError, OSError) as exc:
            result = _rejected("read_rejected", exc)
        return _audit_filesystem_result(
            "fs_read", path, result,
            session_id=authorization["session_id"], profile=authorization["profile"],
        )

    @mcp.tool(name="host_command_profiles")
    def host_command_profiles() -> dict[str, Any]:
        """Describe allowed roots, limits and command profiles (read-only)."""
        authorization, denied = _authorize("host.command.profiles")
        if denied:
            return denied
        result = host_ops.describe_profiles()
        return _audit_result(
            "command_profiles", result,
            session_id=authorization["session_id"], profile=authorization["profile"],
        )

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
        capability_by_profile = {
            "powershell_readonly": "host.command.readonly",
            "git": "host.command.git_read",
            "inspect_d": "host.command.inspect_d",
        }
        capability = capability_by_profile.get(profile)
        if capability is None:
            return {"success": False, "status": "command_rejected", "error": "unsupported command profile"}
        authorization, denied = _authorize(capability)
        if denied:
            return denied
        result = host_ops.run_host_command(
            profile,
            verb,
            arguments,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            confirm_token=confirm_token,
        )
        return _audit_result(
            "command_run", result,
            session_id=authorization["session_id"], profile=authorization["profile"],
            command_profile=profile, verb=verb,
        )

    @mcp.tool(name="host_command_request_confirmation")
    def host_command_request_confirmation(
        profile: str, verb: str, arguments: Sequence[str] | None = None, cwd: str | None = None
    ) -> dict[str, Any]:
        """Issue a single-use token for a confirmable capability, if one exists.

        No host capability is confirmable today; the call reports
        confirmation_not_applicable. It never enables a blocked operation.
        """
        authorization, denied = _authorize("host.command.confirmation")
        if denied:
            return denied
        try:
            argument_values = list(arguments or [])
            result = host_ops.request_confirmation(profile, verb, argument_values, cwd=cwd)
        except (TypeError, ValueError, OSError) as exc:
            argument_values = []
            result = _rejected("confirmation_rejected", exc)
        return _audit_result(
            "confirmation",
            result,
            profile=profile,
            verb=verb,
            argument_count=len(argument_values),
            argument_digest=host_ops._audit_argument_digest(argument_values),
        )

    return TOOL_NAMES


def _rejected(status: str, exc: Exception) -> dict[str, Any]:
    return {
        "success": False,
        "status": status,
        "error": f"{type(exc).__name__}: {exc}",
        "read_only": True,
    }
