"""Run proposed Python files in a disposable, network-isolated Docker container.

The repository snapshot is streamed into the container over stdin. The candidate
never receives a host bind mount, host environment variables, credentials, or
network access. If Docker is unavailable, validation fails closed.
"""
from __future__ import annotations

import ast
import io
import logging
import os
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from app.application.security.repository_path_policy import (
    UnsafeRepositoryPath,
    resolve_repository_path,
)
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "htmlcov", "build", "dist", "backups",
    "evolution_proposals", "sandbox", "logs", "jrvs", ".supabase", ".codex",
    ".claude", ".agents", ".tmp",
}
_EXCLUDED_FILES = {
    ".env", ".gh-token", ".coverage",
    "gatekeeper_rejections.jsonl", "dev_agent_jobs.jsonl",
    "experience_replay.jsonl",
}


class EvolutionSandbox(NexusComponent):
    """Validate a complete candidate file against the repository test suite."""

    def __init__(self) -> None:
        self._enabled: Optional[bool] = None
        self.sandbox_base = Path(tempfile.gettempdir()) / "jarvis-evolution-sandbox"
        self.repository_root = _REPOSITORY_ROOT
        self.timeout = 300
        self.image = os.getenv("EVOLUTION_SANDBOX_IMAGE", "jarvis-evolution-sandbox:latest")

    @property
    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        return os.getenv("SANDBOX_ENABLED", "true").strip().lower() not in {
            "false", "0", "no", "off"
        }

    def configure(self, config: Dict[str, Any]) -> None:
        if "enabled" in config:
            self._enabled = bool(config["enabled"])
        if "sandbox_base" in config:
            self.sandbox_base = Path(config["sandbox_base"])
        if "repository_root" in config:
            self.repository_root = Path(config["repository_root"]).resolve()
        if "timeout" in config:
            self.timeout = max(1, int(config["timeout"]))
        if "image" in config:
            self.image = str(config["image"])

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return self.enabled

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        result = self.test_proposal(
            str(ctx.get("proposal_code", "")),
            str(ctx.get("target_file", "")),
        )
        return {**result, "success": result.get("passed", False)}

    def test_proposal(self, proposal_code: str, target_file: str = "") -> Dict[str, Any]:
        """Apply candidate content to a repository snapshot and run tests in Docker."""
        if not self.enabled:
            return self._failure("sandbox_disabled", "sandbox_disabled")

        if not proposal_code:
            return self._failure("candidate_code_missing", "candidate_code_missing")

        if not target_file:
            return self._failure(
                "candidate_target_missing",
                "target_file is required; standalone snippets are not validated",
            )

        syntax_error = _check_syntax(proposal_code)
        if syntax_error:
            return self._failure("syntax_error", f"syntax_error: {syntax_error}")

        try:
            candidate_path, normalized, _ = resolve_repository_path(
                self.repository_root, target_file, reject_symlinks=True
            )
        except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
            return self._failure("invalid_target_path", f"invalid_target_path: {exc}")

        if candidate_path.suffix.casefold() != ".py":
            return self._failure(
                "invalid_target_type", "candidate target must be a Python source file"
            )
        if not candidate_path.is_file():
            return self._failure(
                "target_file_not_found", f"target_file_not_found: {normalized}"
            )

        try:
            archive = _build_repository_archive(
                self.repository_root, normalized, proposal_code
            )
        except Exception as exc:
            logger.warning("[EvolutionSandbox] Failed to build candidate snapshot: %s", exc)
            return self._failure("snapshot_failed", f"snapshot_failed: {type(exc).__name__}")

        container_name = f"jarvis-evolution-{uuid.uuid4().hex[:12]}"
        command = [
            "docker", "run", "--rm", "-i", "--name", container_name,
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true",
            "--pids-limit", "128",
            "--memory", "4g",
            "--cpus", "2",
            "--user", "65532:65532",
            "--env", "HOME=/tmp",
            "--env", "TMPDIR=/tmp",
            "--tmpfs", "/workspace:rw,nosuid,nodev,size=2g,uid=65532,gid=65532,mode=0755",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m,uid=65532,gid=65532,mode=1777",
            self.image,
            "sh", "-lc",
            "mkdir -p /workspace && tar -xzf - -C /workspace && "
            "cd /workspace && git init -q && "
            "git config user.name JarvisSandbox && "
            "git config user.email sandbox@invalid && "
            "git add -A && git commit -qm candidate && "
            "python -m pytest tests/ --tb=short -x "
            "--no-header -q -o addopts= -p no:cacheprovider",
        ]

        # Docker CLI is trusted host-side code. Do not forward provider, GitHub,
        # Supabase, or application credentials into its process environment.
        clean_env = {"PATH": os.environ.get("PATH", "")}
        if os.name == "nt":
            clean_env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")

        try:
            proc = subprocess.run(
                command,
                input=archive,
                capture_output=True,
                timeout=self.timeout,
                cwd=str(self.repository_root),
                env=clean_env,
                check=False,
            )
        except FileNotFoundError:
            return self._failure(
                "docker_unavailable",
                "docker_unavailable: hardened container runtime is required",
            )
        except subprocess.TimeoutExpired as exc:
            output = _decode_output(exc.stdout) + _decode_output(exc.stderr)
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=10,
                    env=clean_env,
                    check=False,
                )
            except Exception as cleanup_error:
                logger.warning(
                    "[EvolutionSandbox] Container cleanup failed: %s",
                    type(cleanup_error).__name__,
                )
            return {
                "passed": False,
                "test_output": output or "TIMEOUT",
                "errors": [f"timeout_after_{self.timeout}s"],
            }
        except Exception as exc:
            logger.warning("[EvolutionSandbox] Docker execution failed: %s", exc)
            return self._failure(
                "docker_execution_error",
                f"docker_execution_error: {type(exc).__name__}",
            )

        output = _decode_output(proc.stdout) + _decode_output(proc.stderr)
        if proc.returncode != 0:
            return {
                "passed": False,
                "test_output": output,
                "errors": [f"container_tests_failed: exit_code={proc.returncode}"],
            }

        return {"passed": True, "test_output": output, "errors": []}

    @staticmethod
    def _failure(code: str, message: str) -> Dict[str, Any]:
        return {
            "passed": False,
            "test_output": code,
            "errors": [f"{code}: {message}"],
        }


def _build_repository_archive(root: Path, target_file: str, proposal_code: str) -> bytes:
    """Create an in-memory source snapshot, replacing exactly one tracked path."""
    root = root.resolve()
    output = io.BytesIO()
    replaced = False

    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root)
            parts = relative_path.parts
            if not parts or any(part in _EXCLUDED_DIRS for part in parts):
                continue
            if path.is_symlink():
                continue
            if path.is_dir():
                continue
            if path.name in _EXCLUDED_FILES or path.name.startswith(".env."):
                continue
            if path.suffix.casefold() in {".pyc", ".pyo", ".sqlite", ".db", ".log"}:
                continue

            relative = relative_path.as_posix()
            if relative == target_file:
                payload = proposal_code.encode("utf-8")
                info = tarfile.TarInfo(relative)
                info.size = len(payload)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(payload))
                replaced = True
            else:
                archive.add(path, arcname=relative, recursive=False)

        if not replaced:
            raise ValueError("target_file was not included in the repository snapshot")

    return output.getvalue()


def _decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _check_syntax(code: str) -> Optional[str]:
    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return str(exc)
