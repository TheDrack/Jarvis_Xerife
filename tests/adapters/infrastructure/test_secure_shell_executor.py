"""Security tests for the constrained remote PowerShell executor."""

import os
import subprocess
from unittest.mock import patch

import pytest

from app.adapters.infrastructure import secure_shell_executor as executor


@pytest.mark.parametrize(
    "command",
    [
        "Remove-Item C:\\temp\\important.txt",
        "Invoke-Expression 'Get-Process'",
        "Get-Process; Remove-Item C:\\temp\\important.txt",
        "Get-Process | Out-File C:\\temp\\processes.txt",
        "Get-Process $env:SECRET",
        "Start-Process powershell.exe",
        "Get-Service -ComputerName 'remote-host'",
        "Get-NetTCPConnection -CimSession 'remote-host'",
        "Get-Process -OutVariable captured",
        "Get-Content C:\\Users\\USER\\.env",
        "Start-ScheduledTask -TaskName 'Another-Task'",
    ],
)
def test_rejects_commands_outside_the_remote_shell_policy(command):
    with pytest.raises(ValueError):
        executor._validate_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "Get-Process",
        "Get-Process -Name 'python'",
        "Get-Service -Name 'Tailscale'",
        "Get-ScheduledTask -TaskName 'Jarvis-OpenAI-Secure-MCP-Tunnel'",
        "Get-ScheduledTaskInfo -TaskName 'Jarvis-OpenAI-Secure-MCP-Tunnel'",
        "Get-PSDrive -Name 'C'",
        "Get-NetTCPConnection -State Listen",
        "Get-NetAdapter",
        "Get-Date",
        "Get-ComputerInfo",
        "Start-ScheduledTask -TaskName 'Jarvis-OpenAI-Secure-MCP-Tunnel'",
    ],
)
def test_accepts_only_allowlisted_single_powershell_commands(command):
    normalized, command_name = executor._validate_command(command)

    assert normalized == command
    assert command_name == command.split()[0]


def test_rejects_multiline_or_oversized_commands():
    with pytest.raises(ValueError):
        executor._validate_command("Get-Process\nGet-Service")
    with pytest.raises(ValueError):
        executor._validate_command("Get-Process " + ("x" * 2100))


def test_rejects_invalid_timeout():
    with pytest.raises(ValueError):
        executor.run_shell_command("Get-Process", timeout_seconds=0)
    with pytest.raises(ValueError):
        executor.run_shell_command("Get-Process", timeout_seconds=61)
    with pytest.raises(ValueError):
        executor.run_shell_command("Get-Process", timeout_seconds=True)


def test_runner_uses_non_shell_powershell_and_a_sanitized_environment(monkeypatch):
    command = "Get-Process -Name 'python'"
    monkeypatch.setenv("SECRET_TOKEN", "must-not-be-forwarded")
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")
    monkeypatch.setattr(
        executor.shutil,
        "which",
        lambda name: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        if name == "powershell.exe"
        else None,
    )
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='[{"Name":"python","Id":123}]', stderr=""
    )

    with patch.object(executor.subprocess, "run", return_value=completed) as run:
        result = executor.run_shell_command(command, timeout_seconds=12)

    assert result["success"] is True
    assert result["command"] == "Get-Process"
    assert '"Name":"python"' in result["output"]
    args, kwargs = run.call_args
    assert args[0][0].endswith("powershell.exe")
    assert args[0][1:4] == ["-NoLogo", "-NoProfile", "-NonInteractive"]
    assert args[0][4] == "-Command"
    assert "Parser]::ParseInput" in args[0][5]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 12
    assert kwargs["env"]["JARVIS_SHELL_COMMAND"] == command
    assert "SECRET_TOKEN" not in kwargs["env"]
    assert kwargs["cwd"]
    assert "command arguments" not in result



def test_psdrive_projection_serializes_provider_as_a_scalar():
    assert "Provider.Name" in executor._POWERSHELL_WRAPPER
    assert "Name, Provider, Root, Used, Free" not in executor._POWERSHELL_WRAPPER

def test_runner_redacts_and_bounds_command_output(monkeypatch):
    monkeypatch.setattr(
        executor.shutil, "which", lambda name: "C:\\Windows\\powershell.exe"
    )
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"api_key":"super-secret-value"}' + ("x" * 20000),
        stderr="",
    )
    with patch.object(executor.subprocess, "run", return_value=completed):
        result = executor.run_shell_command("Get-Process")

    assert result["truncated"] is True
    assert len(result["output"]) <= executor.MAX_OUTPUT_CHARS
    assert "super-secret-value" not in result["output"]
    assert "[REDACTED]" in result["output"]


def test_runner_returns_bounded_timeout_result(monkeypatch):
    monkeypatch.setattr(
        executor.shutil, "which", lambda name: "C:\\Windows\\powershell.exe"
    )
    timeout = subprocess.TimeoutExpired(
        cmd=["powershell.exe"], timeout=3, output="partial output", stderr=""
    )
    with patch.object(executor.subprocess, "run", side_effect=timeout):
        result = executor.run_shell_command("Get-Process", timeout_seconds=3)

    assert result["success"] is False
    assert result["timed_out"] is True
    assert result["status"] == "timeout"
    assert result["output"] == "partial output"


def test_runner_fails_closed_when_powershell_is_unavailable(monkeypatch):
    monkeypatch.setattr(executor.shutil, "which", lambda name: None)

    result = executor.run_shell_command("Get-Process")

    assert result["success"] is False
    assert result["status"] == "powershell_unavailable"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_windows_runner_executes_an_allowlisted_command_end_to_end():
    result = executor.run_shell_command("Get-Date", timeout_seconds=10)

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["command"] == "Get-Date"
    assert result["output"]
