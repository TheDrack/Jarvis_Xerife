"""Security tests for session gating of the Desktop MCP shell command surface."""

import pytest

pytest.importorskip(
    "mcp",
    reason="The desktop MCP SDK is installed by the edge/Portas test workflow.",
)

from app.adapters.edge import jarvis_desktop_mcp
from app.adapters.infrastructure import session_authorization
from app.adapters.infrastructure.session_authorization import SessionAuthorizationGateway


def test_shell_diagnostics_fail_closed_without_authenticated_session(monkeypatch, tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    monkeypatch.setattr(
        "app.adapters.infrastructure.secure_shell_executor.run_shell_command",
        lambda *args, **kwargs: pytest.fail("shell executor must not run without authorization"),
    )

    result = jarvis_desktop_mcp.run_shell_command("Get-Process")

    assert result["success"] is False
    assert result["status"] == "session_authorization_denied"
    assert result["required_capability"] == "host.command.readonly"


def test_readonly_shell_command_runs_with_observer_session(monkeypatch, tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    pairing = gateway.create_session(profile="observer")
    gateway.authenticate(pairing["pairing_code"])
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    monkeypatch.setattr(
        "app.adapters.infrastructure.secure_shell_executor.run_shell_command",
        lambda command, timeout_seconds: {
            "success": True,
            "status": "completed",
            "read_only": True,
        },
    )

    result = jarvis_desktop_mcp.run_shell_command("Get-Process")

    assert result["success"] is True
    assert result["session_id"] == pairing["session_id"]
    assert result["session_profile"] == "observer"


def test_tunnel_control_command_requires_separate_ungranted_capability(monkeypatch, tmp_path):
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    pairing = gateway.create_session(profile="developer")
    gateway.authenticate(pairing["pairing_code"])
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    monkeypatch.setattr(
        "app.adapters.infrastructure.secure_shell_executor.run_shell_command",
        lambda *args, **kwargs: pytest.fail("tunnel control is not granted by developer profile"),
    )

    result = jarvis_desktop_mcp.run_shell_command(
        'Start-ScheduledTask -TaskName "Jarvis-OpenAI-Secure-MCP-Tunnel"'
    )

    assert result["success"] is False
    assert result["status"] == "session_authorization_denied"
    assert result["required_capability"] == "host.tunnel.control"
