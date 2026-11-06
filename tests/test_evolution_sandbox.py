"""Security and behavior tests for the Docker-backed EvolutionSandbox."""
import io
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.evolution_sandbox import (
    EvolutionSandbox,
    _build_repository_archive,
    _check_syntax,
)


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "app.py").write_text("ORIGINAL = True\n", encoding="utf-8")
    (root / "tests" / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n", encoding="utf-8"
    )
    sb = EvolutionSandbox()
    sb.repository_root = root
    sb.sandbox_base = tmp_path / "sandbox"
    return sb


class TestEvolutionSandboxConfiguration:
    def test_enabled_by_default(self, sandbox, monkeypatch):
        monkeypatch.delenv("SANDBOX_ENABLED", raising=False)
        sandbox._enabled = None
        assert sandbox.enabled is True

    def test_disabled_via_environment(self, sandbox, monkeypatch):
        monkeypatch.setenv("SANDBOX_ENABLED", "false")
        sandbox._enabled = None
        assert sandbox.enabled is False

    def test_configure_can_disable_and_reenable(self, sandbox):
        sandbox.configure({"enabled": False})
        assert sandbox.enabled is False
        sandbox.configure({"enabled": True})
        assert sandbox.enabled is True


class TestCandidateValidation:
    def test_rejects_empty_candidate(self, sandbox):
        result = sandbox.test_proposal("")
        assert result["passed"] is False
        assert "candidate_code_missing" in result["errors"][0]

    def test_rejects_candidate_without_target_file(self, sandbox):
        with patch("app.application.services.evolution_sandbox.subprocess.run") as run:
            result = sandbox.test_proposal("VALUE = 2")
        assert result["passed"] is False
        assert "candidate_target_missing" in result["errors"][0]
        run.assert_not_called()

    def test_rejects_invalid_python_before_container_start(self, sandbox):
        with patch("app.application.services.evolution_sandbox.subprocess.run") as run:
            result = sandbox.test_proposal("def broken(:", "app.py")
        assert result["passed"] is False
        assert "syntax_error" in result["errors"][0]
        run.assert_not_called()

    def test_rejects_path_traversal(self, sandbox):
        result = sandbox.test_proposal("VALUE = 2", "../outside.py")
        assert result["passed"] is False
        assert "invalid_target_path" in result["errors"][0]

    def test_rejects_non_python_target(self, sandbox, tmp_path):
        (sandbox.repository_root / "README.md").write_text("docs", encoding="utf-8")
        result = sandbox.test_proposal("VALUE = 2", "README.md")
        assert result["passed"] is False
        assert "invalid_target_type" in result["errors"][0]

    def test_rejects_missing_target(self, sandbox):
        result = sandbox.test_proposal("VALUE = 2", "missing.py")
        assert result["passed"] is False
        assert "target_file_not_found" in result["errors"][0]


class TestRepositorySnapshot:
    def test_candidate_replaces_target_in_archive(self, sandbox):
        archive_bytes = _build_repository_archive(
            sandbox.repository_root, "app.py", "CANDIDATE = 'new'\n"
        )
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            candidate = archive.extractfile("app.py").read().decode("utf-8")
        assert candidate == "CANDIDATE = 'new'\n"

    def test_snapshot_excludes_git_env_and_local_state(self, sandbox):
        root = sandbox.repository_root
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("secret", encoding="utf-8")
        (root / ".env").write_text("TOKEN=secret", encoding="utf-8")
        (root / "data").mkdir()
        (root / "data" / "local.db").write_text("private", encoding="utf-8")
        archive_bytes = _build_repository_archive(root, "app.py", "SAFE = True\n")
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            names = archive.getnames()
        assert ".git/config" not in names
        assert ".env" not in names
        assert "data/local.db" not in names


class TestDockerExecution:
    def test_runs_candidate_with_hardened_container_and_clean_environment(
        self, sandbox, monkeypatch
    ):
        monkeypatch.setenv("GROQ_API_KEY", "must-not-leak")
        monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
        completed = MagicMock(returncode=0, stdout=b"12 passed", stderr=b"")
        with patch(
            "app.application.services.evolution_sandbox.subprocess.run",
            return_value=completed,
        ) as run:
            result = sandbox.test_proposal("CANDIDATE = True\n", "app.py")

        assert result["passed"] is True
        assert "12 passed" in result["test_output"]
        args = run.call_args.args[0]
        for required in (
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges=true", "--pids-limit", "128",
            "--memory", "4g", "--cpus", "2", "--user", "65532:65532",
        ):
            assert required in args
        assert run.call_args.kwargs["env"].get("GROQ_API_KEY") is None
        assert run.call_args.kwargs["env"].get("GITHUB_TOKEN") is None
        assert run.call_args.kwargs["input"]

    def test_docker_missing_fails_closed(self, sandbox):
        with patch(
            "app.application.services.evolution_sandbox.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = sandbox.test_proposal("CANDIDATE = True\n", "app.py")
        assert result["passed"] is False
        assert "docker_unavailable" in result["errors"][0]

    def test_nonzero_container_exit_fails_validation(self, sandbox):
        completed = MagicMock(returncode=1, stdout=b"FAILED", stderr=b"")
        with patch(
            "app.application.services.evolution_sandbox.subprocess.run",
            return_value=completed,
        ):
            result = sandbox.test_proposal("CANDIDATE = True\n", "app.py")
        assert result["passed"] is False
        assert "container_tests_failed" in result["errors"][0]

    def test_container_timeout_fails_validation(self, sandbox):
        import subprocess

        with patch(
            "app.application.services.evolution_sandbox.subprocess.run",
            side_effect=subprocess.TimeoutExpired("docker", 1, output=b"partial"),
        ):
            result = sandbox.test_proposal("CANDIDATE = True\n", "app.py")
        assert result["passed"] is False
        assert "timeout_after_" in result["errors"][0]


class TestCheckSyntax:
    def test_valid_code_returns_none(self):
        assert _check_syntax("def hello():\n    return True") is None

    def test_invalid_code_returns_message(self):
        assert _check_syntax("def broken(:") is not None

    def test_empty_code_is_valid_python_syntax(self):
        assert _check_syntax("") is None
