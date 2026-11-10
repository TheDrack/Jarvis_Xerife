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
    (repo / ".git").mkdir(parents=True)
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
    assert args[0][0] == "git"
    assert args[0][-3:] == ["status", "--short", "--branch"]
    assert "core.fsmonitor=false" in args[0]
    assert "core.untrackedCache=false" in args[0]
    assert "--no-pager" in args[0]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(repo)
    assert kwargs["timeout"] <= 15
    assert kwargs["env"]["GIT_CEILING_DIRECTORIES"] == str(tmp_path)


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
    (tmp_path / ".git").mkdir()
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
    assert run.call_args.args[0][-4:] == ["log", "--oneline", "-n", "5"]


def test_git_remote_output_redacts_embedded_credentials(tmp_path):
    (tmp_path / ".git").mkdir()
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


def test_cat_redacts_common_secret_values(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"api_key":"very-secret-value","mode":"safe"}', encoding="utf-8"
    )
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat settings.json")

    assert result["success"] is True
    assert "very-secret-value" not in result["output"]
    assert "[REDACTED]" in result["output"]


def test_cat_allows_non_sensitive_file_under_path_containing_secret_word(tmp_path):
    workspace = tmp_path / "secretary-workspace"
    workspace.mkdir()
    (workspace / "settings.json").write_text(
        '{"mode":"safe"}', encoding="utf-8"
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=workspace)

    result = navigator.execute("cat settings.json")

    assert result["success"] is True
    assert result["output"] == '{"mode":"safe"}'


def test_cat_blocks_secret_store_directory_components(tmp_path):
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "settings.json").write_text(
        '{"api_key":"must-not-leak"}', encoding="utf-8"
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=tmp_path)

    result = navigator.execute("cat credentials/settings.json")

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert "must-not-leak" not in result["output"]


def test_ls_hides_cloud_credential_store_directories(tmp_path):
    config = tmp_path / ".config"
    gcloud = config / "gcloud"
    gh = config / "gh"
    gcloud.mkdir(parents=True)
    gh.mkdir()
    (gcloud / "credentials.db").write_text("cloud-secret", encoding="utf-8")
    (gh / "hosts.yml").write_text("oauth_token: secret", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("ls .config")

    assert result["success"] is True
    names = {entry["name"] for entry in json.loads(result["output"])}
    assert "gcloud" not in names
    assert "gh" not in names


def test_cat_blocks_cloud_credential_store_paths(tmp_path):
    credentials = tmp_path / ".config" / "gcloud"
    credentials.mkdir(parents=True)
    (credentials / "credentials.db").write_text("cloud-secret", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat .config/gcloud/credentials.db")

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert "cloud-secret" not in result["output"]


def test_git_rejects_repository_config_that_can_execute_commands(tmp_path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        "[core]\n\tfsmonitor = !touch /tmp/jarvis-should-not-run\n",
        encoding="utf-8",
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git status")

    assert result["success"] is False
    assert result["status"] == "git_config_rejected"
    run.assert_not_called()


def test_git_does_not_discover_repository_above_allowed_root(tmp_path):
    outer_repo = tmp_path / "outer"
    (outer_repo / ".git").mkdir(parents=True)
    allowed = outer_repo / "allowed"
    allowed.mkdir()
    navigator = ShellNavigator(allowed_roots=[allowed], initial_directory=allowed)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git status")

    assert result["success"] is False
    assert result["status"] == "git_repository_outside_allowed_roots"
    run.assert_not_called()


def test_git_remote_redacts_token_only_url_userinfo(tmp_path):
    (tmp_path / ".git").mkdir()
    navigator = make_navigator(tmp_path)
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0,
        stdout="origin https://ghp_supersecretvalue@github.com/org/repo.git (fetch)",
        stderr="",
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=completed,
    ):
        result = navigator.execute("git remote -v")

    assert result["success"] is True
    assert "ghp_supersecretvalue" not in result["output"]
    assert "[REDACTED]" in result["output"]


def test_mixed_separator_unc_is_rejected_before_path_resolution(tmp_path, monkeypatch):
    navigator = make_navigator(tmp_path)
    original = Path.resolve

    def guarded_resolve(path, *args, **kwargs):
        if str(path).startswith("\\\\") or str(path).startswith("//"):
            raise AssertionError("network path resolution must not be attempted")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    result = navigator.execute('cat "\\\\attacker.example/share/secret.txt"')

    assert result["success"] is False
    assert result["status"] == "path_outside_allowed_roots"


def test_cat_blocks_additional_developer_credential_store_paths(tmp_path):
    relative_paths = (
        ".config/glab-cli/config.yml",
        ".config/github-copilot/hosts.json",
        ".config/composer/auth.json",
        ".config/age/keys.txt",
        ".config/ngrok/ngrok.yml",
        ".m2/settings.xml",
        ".yarnrc.yml",
    )
    for relative in relative_paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("oauth_token: do-not-disclose", encoding="utf-8")

    navigator = make_navigator(tmp_path)
    for relative in relative_paths:
        result = navigator.execute(f'cat "{relative}"')
        assert result["success"] is False
        assert result["status"] == "sensitive_file_blocked"


def test_cat_blocks_files_containing_stored_credential_markers(tmp_path):
    target = tmp_path / "settings.xml"
    target.write_text(
        "<settings><password>xml-secret-value</password></settings>",
        encoding="utf-8",
    )
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat settings.xml")

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert "xml-secret-value" not in result["output"]


def test_git_show_rejects_blob_object_targets(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)
    failed_probe = subprocess.CompletedProcess(
        args=["git", "rev-parse"], returncode=1, stdout="", stderr=""
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=failed_probe,
    ) as run:
        result = navigator.execute("git show --stat deadbeef")

    assert result["success"] is False
    assert result["status"] == "command_rejected"
    run.assert_called_once()


def test_git_show_accepts_commit_targets_and_keeps_metadata_only_flags(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)
    probe = subprocess.CompletedProcess(
        args=["git", "rev-parse"], returncode=0, stdout="deadbeef", stderr=""
    )
    command = subprocess.CompletedProcess(
        args=["git", "show"], returncode=0, stdout="commit 123\n 1 file changed", stderr=""
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        side_effect=[probe, command],
    ) as run:
        result = navigator.execute("git show --stat HEAD")

    assert result["success"] is True
    assert "1 file changed" in result["output"]
    assert run.call_count == 2
