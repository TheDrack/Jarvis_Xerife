from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from app.adapters.infrastructure import termux_shell_mcp_tools as shell_mcp
from app.adapters.infrastructure import termux_shell


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name=None, **_options):
        def decorate(function):
            self.tools[name or function.__name__] = function
            return function
        return decorate


def _gateway(tmp_path):
    from app.adapters.infrastructure.session_authorization import SessionAuthorizationGateway
    return SessionAuthorizationGateway(
        tmp_path / "session.json",
        clock=lambda: datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
    )


def test_session_tools_are_always_registered_but_shell_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_ANDROID_SHELL_ENABLED", raising=False)
    gateway = _gateway(tmp_path)
    monkeypatch.setattr(shell_mcp, "SESSION_GATEWAY", gateway)
    mcp = FakeMCP()

    registered = shell_mcp.register_termux_shell_tools(mcp)

    assert set(registered) == {
        "android_shell_session_authenticate",
        "android_shell_session_status",
        "android_shell_session_revoke",
    }
    assert set(mcp.tools) == set(registered)
    assert "android_shell_exec" not in mcp.tools


def test_shell_tool_requires_single_use_termux_session(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_ANDROID_SHELL_ENABLED", "1")
    gateway = _gateway(tmp_path)
    monkeypatch.setattr(shell_mcp, "SESSION_GATEWAY", gateway)
    mcp = FakeMCP()
    shell_mcp.register_termux_shell_tools(mcp)

    denied = mcp.tools["android_shell_exec"]("printf blocked")

    assert denied["success"] is False
    assert denied["status"] == "session_authorization_denied"

    created = gateway.create_session(profile="termux_developer", ttl_minutes=30)
    paired = mcp.tools["android_shell_session_authenticate"](created["pairing_code"])
    assert paired["success"] is True
    assert paired["authenticated"] is True

    monkeypatch.setattr(
        termux_shell,
        "run_shell_command",
        lambda command, cwd=None, timeout_seconds=30: {
            "success": True, "stdout": command, "stderr": "", "exit_code": 0,
            "timed_out": False, "cwd": cwd, "duration_ms": 1, "shell": True,
            "elevated": False,
        },
    )
    result = mcp.tools["android_shell_exec"]("printf authorized")

    assert result["success"] is True
    assert result["stdout"] == "printf authorized"
    with pytest.raises(Exception):
        gateway.authenticate(created["pairing_code"])


def test_shell_executor_runs_shell_syntax_as_termux_user(tmp_path):
    result = termux_shell.run_shell_command(
        "value='Jarvis'; printf '%s\\n' \"$value\"",
        cwd=str(tmp_path),
        timeout_seconds=5,
    )

    assert result["success"] is True
    assert result["stdout"].strip() == "Jarvis"
    assert result["exit_code"] == 0
    assert result["shell"] is True
    assert result["elevated"] is False


def test_shell_executor_times_out_and_terminates_process_group(tmp_path):
    result = termux_shell.run_shell_command(
        "sleep 5",
        cwd=str(tmp_path),
        timeout_seconds=1,
    )

    assert result["success"] is False
    assert result["timed_out"] is True
    assert result["exit_code"] is None


@pytest.mark.parametrize(
    ("command", "cwd", "timeout"),
    [
        ("", None, 10),
        ("x" * 8193, None, 10),
        ("printf ok", "/path/that/does/not/exist", 10),
        ("printf ok", None, 0),
        ("printf ok", None, 121),
        ("printf ok", None, True),
    ],
)
def test_shell_executor_rejects_invalid_inputs(command, cwd, timeout):
    with pytest.raises(ValueError):
        termux_shell.run_shell_command(command, cwd=cwd, timeout_seconds=timeout)


def test_shell_audit_records_digest_without_command_or_output(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(termux_shell, "AUDIT_LOG", audit)

    result = termux_shell.run_shell_command(
        "printf PRIVATE_COMMAND_OUTPUT",
        cwd=str(tmp_path),
        timeout_seconds=5,
    )

    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert result["success"] is True
    assert records[-1]["command_sha256"]
    assert "PRIVATE_COMMAND_OUTPUT" not in audit.read_text(encoding="utf-8")
    assert "printf PRIVATE_COMMAND_OUTPUT" not in audit.read_text(encoding="utf-8")
