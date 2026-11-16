"""MCP registration for the session-gated Termux shell executor."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.adapters.infrastructure import termux_shell
from app.adapters.infrastructure.session_authorization import (
    SESSION_GATEWAY,
    SessionAuthorizationError,
)

logger = logging.getLogger(__name__)

SESSION_TOOL_NAMES = (
    "android_shell_session_authenticate",
    "android_shell_session_status",
    "android_shell_session_revoke",
)
SHELL_TOOL_NAMES = ("android_shell_exec",)


def register_termux_shell_tools(mcp: Any) -> tuple[str, ...]:
    """Register pairing controls; expose arbitrary shell only after local opt-in."""

    @mcp.tool(name="android_shell_session_authenticate")
    def android_shell_session_authenticate(pairing_code: str) -> dict[str, Any]:
        """Consume a one-time local pairing code for an approved Termux session profile."""
        try:
            result = SESSION_GATEWAY.authenticate(pairing_code)
            audit_logged = termux_shell.audit_event(
                "session_authenticated",
                session_id=result["session_id"],
                profile=result["profile"],
            )
            return {"success": True, **result, "audit_logged": audit_logged}
        except SessionAuthorizationError as exc:
            logger.warning("Termux shell session pairing rejected: %s", str(exc))
            audit_logged = termux_shell.audit_event("session_authentication_denied")
            return {
                "success": False,
                "status": "authentication_denied",
                "error": str(exc),
                "audit_logged": audit_logged,
            }

    @mcp.tool(name="android_shell_session_status")
    def android_shell_session_status() -> dict[str, Any]:
        """Return non-secret metadata for the current Termux shell session."""
        return SESSION_GATEWAY.status()

    @mcp.tool(name="android_shell_session_revoke")
    def android_shell_session_revoke() -> dict[str, Any]:
        """Revoke the current Termux shell session immediately."""
        result = SESSION_GATEWAY.revoke()
        result["audit_logged"] = termux_shell.audit_event(
            "session_revoked", session_id=result.get("session_id")
        )
        return result

    enabled = os.environ.get("JARVIS_ANDROID_SHELL_ENABLED", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info(
            "Termux shell execution is disabled; pairing controls remain available"
        )
        return SESSION_TOOL_NAMES

    def _authorize() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            return SESSION_GATEWAY.require("android.shell.exec"), None
        except SessionAuthorizationError as exc:
            audit_logged = termux_shell.audit_event(
                "shell_authorization_denied", capability="android.shell.exec"
            )
            return None, {
                "success": False,
                "status": "session_authorization_denied",
                "error": str(exc),
                "audit_logged": audit_logged,
            }

    @mcp.tool(name="android_shell_exec")
    def android_shell_exec(
        command: str,
        cwd: str | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Run arbitrary Bash in the unprivileged Termux app sandbox.

        Commands may read/write Termux-accessible files, install packages and
        manage Termux processes. This tool does not request Android root.
        Requires a locally issued, single-use termux_developer pairing code.
        """
        authorization, denied = _authorize()
        if denied:
            return denied
        try:
            result = termux_shell.run_shell_command(
                command,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                session_id=authorization["session_id"],
            )
        except (TypeError, ValueError, OSError, RuntimeError) as exc:
            result = {
                "success": False,
                "status": "command_rejected",
                "error": f"{type(exc).__name__}: {exc}",
                "elevated": False,
            }
            termux_shell.audit_event(
                "shell_command_rejected", session_id=authorization["session_id"]
            )
        result["session_id"] = authorization["session_id"]
        result["profile"] = authorization["profile"]
        return result

    return SESSION_TOOL_NAMES + SHELL_TOOL_NAMES
