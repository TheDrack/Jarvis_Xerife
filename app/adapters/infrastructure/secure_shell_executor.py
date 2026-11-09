"""Constrained PowerShell execution exposed through the authenticated Jarvis MCP tunnel.

This is intentionally not a general-purpose remote shell. It accepts one simple
PowerShell command from a small allowlist, blocks shell composition/dynamic code,
runs without elevation and forwards only a minimal environment. The sole
state-changing operation is starting the dedicated Jarvis tunnel scheduled task.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_COMMAND_CHARS = 2048
MAX_OUTPUT_CHARS = 16_000
MAX_ERROR_CHARS = 4_000
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60

_READ_ONLY_COMMANDS = frozenset(
    {
        "Get-Process",
        "Get-Service",
        "Get-ScheduledTask",
        "Get-ScheduledTaskInfo",
        "Get-PSDrive",
        "Get-NetTCPConnection",
        "Get-NetAdapter",
        "Get-Date",
        "Get-ComputerInfo",
    }
)
_START_TASK_COMMAND = "Start-ScheduledTask"
_ALLOWED_COMMANDS = _READ_ONLY_COMMANDS | {_START_TASK_COMMAND}
_ALLOWED_PARAMETERS = {
    "Get-Process": frozenset({"Name", "Id"}),
    "Get-Service": frozenset({"Name", "DisplayName"}),
    "Get-ScheduledTask": frozenset({"TaskName", "TaskPath", "State"}),
    "Get-ScheduledTaskInfo": frozenset({"TaskName", "TaskPath"}),
    "Get-PSDrive": frozenset({"Name", "PSProvider"}),
    "Get-NetTCPConnection": frozenset({"State", "LocalPort", "RemotePort", "OwningProcess"}),
    "Get-NetAdapter": frozenset({"Name", "InterfaceDescription", "Physical"}),
    "Get-Date": frozenset(),
    "Get-ComputerInfo": frozenset({"Property"}),
    "Start-ScheduledTask": frozenset({"TaskName"}),
}
_PARAMETER_NAME = re.compile(r"(?<!\\S)-([A-Za-z][A-Za-z0-9]*)\\b")
_FORBIDDEN_SYNTAX = re.compile(r"[\x00\r\n;|&`$<>{}\[\]()]" )
_COMMAND_NAME = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)\b")
_START_TUNNEL_TASK = re.compile(
    r"""^Start-ScheduledTask\s+-TaskName\s+(?:'Jarvis-OpenAI-Secure-MCP-Tunnel'|"Jarvis-OpenAI-Secure-MCP-Tunnel"|Jarvis-OpenAI-Secure-MCP-Tunnel)$""",
    re.IGNORECASE,
)

# This wrapper parses the supplied text before executing it. Only a single
# literal command AST is accepted; variables, script blocks, pipelines,
# redirection, member invocation and dynamic command names are rejected.
_POWERSHELL_WRAPPER = r"""
$ErrorActionPreference = 'Stop'
$source = $env:JARVIS_SHELL_COMMAND
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $source, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    [Console]::Error.WriteLine('PowerShell syntax rejected.')
    exit 64
}
$statements = @($ast.EndBlock.Statements)
if ($statements.Count -ne 1 -or
    $statements[0] -isnot [System.Management.Automation.Language.PipelineAst]) {
    [Console]::Error.WriteLine('Only one simple command is permitted.')
    exit 64
}
$pipeline = $statements[0]
if ($pipeline.PipelineElements.Count -ne 1 -or
    $pipeline.PipelineElements[0] -isnot [System.Management.Automation.Language.CommandAst]) {
    [Console]::Error.WriteLine('Pipelines and compound commands are not permitted.')
    exit 64
}
$commandAst = $pipeline.PipelineElements[0]
if ($commandAst.InvocationOperator -ne [System.Management.Automation.Language.TokenKind]::Unknown) {
    [Console]::Error.WriteLine('Dynamic command invocation is not permitted.')
    exit 64
}
$commandName = $commandAst.GetCommandName()
$allowedCommands = @(
    'Get-Process', 'Get-Service', 'Get-ScheduledTask', 'Get-ScheduledTaskInfo',
    'Get-PSDrive', 'Get-NetTCPConnection', 'Get-NetAdapter', 'Get-Date',
    'Get-ComputerInfo', 'Start-ScheduledTask'
)
if ($allowedCommands -notcontains $commandName) {
    [Console]::Error.WriteLine('Command is not allowlisted.')
    exit 65
}
$allowedParameters = @{
    'Get-Process' = @('Name', 'Id')
    'Get-Service' = @('Name', 'DisplayName')
    'Get-ScheduledTask' = @('TaskName', 'TaskPath', 'State')
    'Get-ScheduledTaskInfo' = @('TaskName', 'TaskPath')
    'Get-PSDrive' = @('Name', 'PSProvider')
    'Get-NetTCPConnection' = @('State', 'LocalPort', 'RemotePort', 'OwningProcess')
    'Get-NetAdapter' = @('Name', 'InterfaceDescription', 'Physical')
    'Get-Date' = @()
    'Get-ComputerInfo' = @('Property')
    'Start-ScheduledTask' = @('TaskName')
}
foreach ($element in $commandAst.CommandElements) {
    if ($element -is [System.Management.Automation.Language.CommandParameterAst] -and
        $allowedParameters[$commandName] -notcontains $element.ParameterName) {
        [Console]::Error.WriteLine('Command parameter is not allowlisted.')
        exit 65
    }
}
$allowedNodeTypes = @(
    'ScriptBlockAst', 'NamedBlockAst', 'StatementBlockAst', 'PipelineAst',
    'CommandAst', 'CommandParameterAst', 'StringConstantExpressionAst',
    'ConstantExpressionAst'
)
$unsafeNodes = $ast.FindAll({
    param($node)
    $allowedNodeTypes -notcontains $node.GetType().Name
}, $true)
if ($unsafeNodes.Count -gt 0) {
    [Console]::Error.WriteLine('Dynamic expressions, variables and nested script blocks are not permitted.')
    exit 64
}
if ($commandName -eq 'Start-ScheduledTask' -and
    $source -notmatch '^Start-ScheduledTask\s+-TaskName\s+(''Jarvis-OpenAI-Secure-MCP-Tunnel''|"Jarvis-OpenAI-Secure-MCP-Tunnel"|Jarvis-OpenAI-Secure-MCP-Tunnel)$') {
    [Console]::Error.WriteLine('Only the dedicated Jarvis tunnel task may be started.')
    exit 65
}

$engine = [System.Management.Automation.PowerShell]::Create()
try {
    [void]$engine.AddScript($source)
    $items = @($engine.Invoke())
    if ($engine.HadErrors) {
        $errorText = @($engine.Streams.Error | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        [Console]::Error.WriteLine($errorText)
        exit 1
    }
    switch ($commandName) {
        'Get-Process' {
            $safeItems = @($items | Select-Object -First 100 Name, Id, CPU, WorkingSet64, Responding)
        }
        'Get-Service' {
            $safeItems = @($items | Select-Object -First 100 Name, Status, StartType)
        }
        'Get-ScheduledTask' {
            $safeItems = @($items | Select-Object -First 100 TaskName, State, TaskPath, Author, Description)
        }
        'Get-ScheduledTaskInfo' {
            $safeItems = @($items | Select-Object -First 100 TaskName, LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns)
        }
        'Get-PSDrive' {
            $safeItems = @($items | Select-Object -First 100 Name, Provider, Root, Used, Free)
        }
        'Get-NetTCPConnection' {
            $safeItems = @($items | Select-Object -First 100 LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess)
        }
        'Get-NetAdapter' {
            $safeItems = @($items | Select-Object -First 100 Name, Status, LinkSpeed, MacAddress)
        }
        'Get-ComputerInfo' {
            $safeItems = @($items | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture, CsName, CsTotalPhysicalMemory)
        }
        default {
            $safeItems = @($items)
        }
    }
    $json = ConvertTo-Json -InputObject @($safeItems) -Depth 4 -Compress
    [Console]::Out.WriteLine($json)
}
finally {
    $engine.Dispose()
}
"""


def _validate_command(command: str) -> tuple[str, str]:
    """Validate one literal command against the local remote-execution policy."""
    if not isinstance(command, str):
        raise ValueError("command must be a string")
    normalized = command.strip()
    if not normalized or len(normalized) > MAX_COMMAND_CHARS:
        raise ValueError(f"command must contain 1 to {MAX_COMMAND_CHARS} characters")
    if _FORBIDDEN_SYNTAX.search(normalized):
        raise ValueError("shell operators, variables, multiline and dynamic syntax are not permitted")
    match = _COMMAND_NAME.match(normalized)
    if match is None:
        raise ValueError("command name is invalid")
    command_name = match.group(1)
    canonical_name = next(
        (name for name in _ALLOWED_COMMANDS if name.casefold() == command_name.casefold()),
        None,
    )
    if canonical_name is None:
        raise ValueError("command is not allowlisted")
    supplied_parameters = _PARAMETER_NAME.findall(normalized)
    allowed_parameters = _ALLOWED_PARAMETERS[canonical_name]
    if any(parameter.casefold() not in {item.casefold() for item in allowed_parameters} for parameter in supplied_parameters):
        raise ValueError("command parameter is not allowlisted")
    if canonical_name == _START_TASK_COMMAND and not _START_TUNNEL_TASK.fullmatch(normalized):
        raise ValueError("only the dedicated Jarvis tunnel scheduled task may be started")
    return normalized, canonical_name


def _safe_environment(command: str) -> dict[str, str]:
    """Build a minimal process environment with only system PowerShell modules."""
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\\Windows"
    program_files = os.environ.get("ProgramFiles") or r"C:\\Program Files"
    module_paths = [
        os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"),
        os.path.join(program_files, "WindowsPowerShell", "Modules"),
    ]
    environment = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "ProgramData", "ProgramFiles")
        if key in os.environ
    }
    environment["PSModulePath"] = os.pathsep.join(module_paths)
    environment["JARVIS_SHELL_COMMAND"] = command
    environment["POWERSHELL_TELEMETRY_OPTOUT"] = "1"
    return environment


def _redact(value: str) -> str:
    """Remove common credential forms before returning command output to the caller."""
    value = re.sub(
        r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]{16,}", "[REDACTED_API_KEY]", value)
    value = re.sub(
        r"""(?i)(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)["']?\s*[:=]\s*["']?)[^"'\s,}]+""",
        r"\1[REDACTED]",
        value,
    )
    return value


def _bounded(value: str, limit: int) -> tuple[str, bool]:
    redacted = _redact(value or "")
    return redacted[:limit], len(redacted) > limit


def run_shell_command(command: str, *, timeout_seconds: int = 15) -> dict[str, Any]:
    """Run one allowlisted PowerShell diagnostic or the dedicated tunnel start action.

    Commands run as the current non-elevated Jarvis user. The API accepts no
    arbitrary executable, working directory, environment, shell operators,
    pipelines, file reads, process termination or privilege changes.
    """
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise ValueError("timeout_seconds must be an integer")
    if not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS}"
        )
    normalized, command_name = _validate_command(command)
    executable = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not executable:
        return {
            "success": False,
            "status": "powershell_unavailable",
            "command": command_name,
            "message": "Windows PowerShell or PowerShell 7 was not found on PATH.",
        }

    repository_root = Path(__file__).resolve().parents[3]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _POWERSHELL_WRAPPER,
            ],
            cwd=str(repository_root),
            env=_safe_environment(normalized),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output, truncated = _bounded(
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            MAX_OUTPUT_CHARS,
        )
        error, _ = _bounded(
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or ""),
            MAX_ERROR_CHARS,
        )
        logger.warning("Restricted shell command timed out: %s", command_name)
        return {
            "success": False,
            "status": "timeout",
            "command": command_name,
            "output": output,
            "error": error,
            "timed_out": True,
            "truncated": truncated,
            "timeout_seconds": timeout_seconds,
        }
    except OSError as exc:
        logger.error("Restricted shell launch failed: %s", type(exc).__name__)
        return {
            "success": False,
            "status": "execution_failed",
            "command": command_name,
            "error": type(exc).__name__,
        }

    output, output_truncated = _bounded(completed.stdout, MAX_OUTPUT_CHARS)
    error, error_truncated = _bounded(completed.stderr, MAX_ERROR_CHARS)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    success = completed.returncode == 0
    logger.info(
        "Restricted shell command=%s success=%s exit_code=%s elapsed_ms=%s",
        command_name,
        success,
        completed.returncode,
        elapsed_ms,
    )
    return {
        "success": success,
        "status": "completed" if success else "command_failed",
        "command": command_name,
        "output": output,
        "error": error,
        "exit_code": completed.returncode,
        "timed_out": False,
        "truncated": output_truncated or error_truncated,
        "elapsed_ms": elapsed_ms,
        "execution_mode": "non_elevated_allowlist",
    }
