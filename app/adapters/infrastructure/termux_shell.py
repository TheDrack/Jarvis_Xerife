"""Authenticated arbitrary shell execution in the unprivileged Termux user context.

This is intentionally opt-in and session-gated. It invokes Bash without root
escalation, bounds runtime and captured output, and audits only digests/metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_COMMAND_CHARS = 8192
MAX_TIMEOUT_SECONDS = 120
MAX_STDOUT_BYTES = 32 * 1024
MAX_STDERR_BYTES = 16 * 1024
AUDIT_LOG = Path(
    os.environ.get(
        "JARVIS_ANDROID_SHELL_AUDIT_LOG",
        str(Path.home() / ".local/state/jarvis/android_shell_audit.jsonl"),
    )
)
_EXECUTION_LOCK = threading.Lock()
_AUDIT_LOCK = threading.Lock()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _append_audit(record: dict[str, Any]) -> bool:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            AUDIT_LOG.parent.chmod(0o700)
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with _AUDIT_LOCK:
            descriptor = os.open(AUDIT_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                if os.name != "nt":
                    os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "a", encoding="utf-8", closefd=False) as stream:
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                os.close(descriptor)
        return True
    except OSError:
        return False


def audit_event(event: str, **metadata: Any) -> bool:
    """Write secret-free session metadata to the local audit log."""
    return _append_audit({
        "audit_id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **metadata,
    })


def _bounded_reader(
    stream: Any, limit: int, output: bytearray, truncated: list[bool]
) -> None:
    while True:
        chunk = stream.read(8192)
        if not chunk:
            return
        remaining = limit - len(output)
        if remaining > 0:
            output.extend(chunk[:remaining])
        if len(chunk) > max(remaining, 0):
            truncated[0] = True


def run_shell_command(
    command: str,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 30,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute a Bash command as the current Termux app user, never via su/sudo."""
    if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_CHARS:
        raise ValueError(f"command must contain 1-{MAX_COMMAND_CHARS} characters")
    if "\x00" in command:
        raise ValueError("command cannot contain NUL")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise ValueError("timeout_seconds must be an integer")
    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")

    working_directory = Path(cwd).expanduser() if cwd is not None else Path.home()
    try:
        working_directory = working_directory.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("cwd must resolve to an existing directory") from exc
    if not working_directory.is_dir():
        raise ValueError("cwd must be an existing directory")

    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("Bash is not available in the Termux PATH")

    started = time.monotonic()
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    stdout_was_truncated = [False]
    stderr_was_truncated = [False]
    timed_out = False
    exit_code: int | None = None

    with _EXECUTION_LOCK:
        process = subprocess.Popen(
            [bash, "--noprofile", "--norc", "-c", command],
            cwd=str(working_directory),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=(os.name != "nt"),
            close_fds=True,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(
            target=_bounded_reader,
            args=(process.stdout, MAX_STDOUT_BYTES, stdout_buffer, stdout_was_truncated),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_bounded_reader,
            args=(process.stderr, MAX_STDERR_BYTES, stderr_buffer, stderr_was_truncated),
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
            exit_code = None
        finally:
            # Do not leave background children running after the shell request ends.
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            process.stdout.close()
            process.stderr.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_truncated = stdout_was_truncated[0]
    stderr_truncated = stderr_was_truncated[0]
    audit_logged = audit_event(
        "shell_command",
        session_id=session_id,
        command_sha256=_sha256(command),
        cwd_sha256=_sha256(str(working_directory)),
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=duration_ms,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )
    return {
        "success": not timed_out and exit_code == 0,
        "status": "timed_out" if timed_out else "completed",
        "stdout": stdout_buffer.decode("utf-8", errors="replace"),
        "stderr": stderr_buffer.decode("utf-8", errors="replace"),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "cwd": str(working_directory),
        "duration_ms": duration_ms,
        "shell": True,
        "elevated": False,
        "audit_logged": audit_logged,
    }
