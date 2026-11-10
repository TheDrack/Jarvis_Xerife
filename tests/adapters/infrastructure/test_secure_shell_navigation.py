"""Tests for the read-only shell navigation exposed through the MCP tunnel."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.adapters.infrastructure.secure_shell_navigation import ShellNavigator


def make_navigator(tmp_path: Path) -> ShellNavigator:
    return ShellNavigator(allowed_roots=[tmp_path], initial_directory=tmp_path)


def test_pwd_and_cd_keep_a_stateful_working_directory(tmp_path):
    (tmp_path / "Jarvis Project").mkdir()
    navigator = make_navigator(tmp_path)

    changed = navigator.execute('cd "Jarvis Project"')
    current = navigator.execute("pwd")

    assert changed["success"] is True
    assert Path(current["output"]) == (tmp_path / "Jarvis Project").resolve()


def test_ls_returns_bounded_metadata_without_reading_file_contents(tmp_path):
    (tmp_path / "README.md").write_text("do not include this content", encoding="utf-8")
    (tmp_path / "src").mkdir()
    navigator = make_navigator(tmp_path)

    result = navigator.execute("ls")

    assert result["success"] is True
    entries = json.loads(result["output"])
    assert {entry["name"] for entry in entries} == {"README.md", "src"}
    assert all("content" not in entry for entry in entries)


def test_cat_reads_only_bounded_non_sensitive_text_files(tmp_path):
    (tmp_path / "README.md").write_text("Jarvis OS", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat README.md")

    assert result["success"] is True
    assert result["output"] == "Jarvis OS"


@pytest.mark.parametrize("filename", [".env", "id_rsa", "secrets.json", "credentials.txt"])
def test_cat_rejects_sensitive_file_names(tmp_path, filename):
    (tmp_path / filename).write_text("sensitive-value", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cat "{filename}"')

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert "sensitive-value" not in result["output"]


def test_navigation_rejects_paths_outside_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("private", encoding="utf-8")
    navigator = ShellNavigator(allowed_roots=[allowed], initial_directory=allowed)

    result = navigator.execute(f'cat "{outside / "secret.txt"}"')

    assert result["success"] is False
    assert result["status"] == "path_outside_allowed_roots"


@pytest.mark.parametrize(
    "command",
    [
        "Get-Content .env",
        "cat README.md; whoami",
        "pwd | Out-File result.txt",
        "git status && git clean -fd",
        "cat $env:SECRET",
        "Start-Process powershell",
        "Remove-Item README.md",
    ],
)
def test_rejects_shell_composition_and_unlisted_commands(tmp_path, command):
    navigator = make_navigator(tmp_path)

    result = navigator.execute(command)

    assert result["success"] is False
    assert result["status"] == "command_rejected"


def test_git_status_runs_as_argv_without_shell_and_uses_current_directory(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="## main", stderr=""
    )

    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=completed,
    ) as run:
        result = navigator.execute("git status --short --branch")

    assert result["success"] is True
    assert result["output"] == "## main"
    args, kwargs = run.call_args
    assert args[0] == [
        "git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "status", "--short", "--branch",
    ]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(repo)
    assert kwargs["timeout"] <= 15


def test_git_rejects_mutating_subcommands(tmp_path):
    navigator = make_navigator(tmp_path)

    result = navigator.execute("git reset --hard")

    assert result["success"] is False
    assert result["status"] == "command_rejected"


def test_cat_rejects_oversized_files_without_returning_partial_secret(tmp_path):
    (tmp_path / "large.txt").write_text("x" * 100, encoding="utf-8")
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=tmp_path, max_read_bytes=32)

    result = navigator.execute("cat large.txt")

    assert result["success"] is False
    assert result["status"] == "file_too_large"
    assert result["output"] == ""


def test_ls_caps_number_of_entries(tmp_path):
    for index in range(5):
        (tmp_path / f"file-{index}.txt").touch()
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=tmp_path, max_entries=2)

    result = navigator.execute("ls")

    assert result["success"] is True
    assert len(json.loads(result["output"])) == 2
    assert result["truncated"] is True



def test_git_log_supports_a_bounded_commit_count(tmp_path):
    navigator = make_navigator(tmp_path)
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="abc123 initial", stderr=""
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=completed,
    ) as run:
        result = navigator.execute("git log --oneline -n 5")

    assert result["success"] is True
    assert run.call_args.args[0][-5:] == ["log", "--oneline", "-n", "5"]


def test_git_remote_output_redacts_embedded_credentials(tmp_path):
    navigator = make_navigator(tmp_path)
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0,
        stdout="origin https://user:supersecret@example.com/org/repo.git (fetch)",
        stderr="",
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=completed,
    ):
        result = navigator.execute("git remote -v")

    assert result["success"] is True
    assert "supersecret" not in result["output"]
    assert "[REDACTED]" in result["output"]
