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
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run"
    ) as run:
        result = navigator.execute("git show --stat deadbeef")

    assert result["success"] is False
    assert result["status"] == "command_rejected"
    run.assert_not_called()


def test_git_show_accepts_only_the_fixed_metadata_command(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)
    command = subprocess.CompletedProcess(
        args=["git", "show"], returncode=0, stdout="commit 123\\n 1 file changed", stderr=""
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=command,
    ) as run:
        result = navigator.execute("git show --stat --oneline -1")

    assert result["success"] is True
    assert "1 file changed" in result["output"]
    run.assert_called_once()


def test_cat_redacts_json_credential_assignments(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(
        '{"api_key":"api-secret-value","oauth_token":"oauth-secret-value",'
        '"client_secret":"client-secret-value"}',
        encoding="utf-8",
    )
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat settings.json")

    assert result["success"] is True
    assert "api-secret-value" not in result["output"]
    assert "oauth-secret-value" not in result["output"]
    assert "client-secret-value" not in result["output"]
    assert result["output"].count("[REDACTED]") == 3


def test_default_allowed_roots_do_not_include_entire_user_profile(monkeypatch):
    from app.adapters.infrastructure import secure_shell_navigation as module

    monkeypatch.delenv("JARVIS_SHELL_ALLOWED_ROOTS", raising=False)
    navigator = ShellNavigator()
    repository_root = Path(module.__file__).resolve().parents[3]

    assert repository_root in navigator.allowed_roots
    assert Path.home().resolve() not in navigator.allowed_roots


def test_ls_bounds_raw_scandir_work_even_when_entries_are_sensitive(tmp_path, monkeypatch):
    from app.adapters.infrastructure import secure_shell_navigation as module

    for index in range(20):
        (tmp_path / f".env.secret-{index}").touch()
    (tmp_path / "visible.txt").touch()
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=tmp_path, max_entries=4)

    original_scandir = module.os.scandir
    observed = {"count": 0}

    class BoundedIterator:
        def __init__(self, path):
            self._iterator = original_scandir(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._iterator.close()

        def __iter__(self):
            return self

        def __next__(self):
            observed["count"] += 1
            return next(self._iterator)

    monkeypatch.setattr(module.os, "scandir", BoundedIterator)
    result = navigator.execute("ls")

    assert result["success"] is True
    assert result["truncated"] is True
    assert observed["count"] == 5
    assert json.loads(result["output"]) == []


@pytest.mark.parametrize(
    "content",
    [
        '{"oauth_token": "ordinary-oauth-secret-value"}',
        '{"accessToken": "ordinary-access-secret-value"}',
        '{"refresh_token": "ordinary-refresh-secret-value"}',
        '{"client_secret": "ordinary-client-secret-value"}',
        '{"private_key": "ordinary-private-key-value"}',
        '{"auths": {"registry.example": {"auth": "encoded-secret"}}}',
    ],
)
def test_cat_rejects_common_credential_store_content(tmp_path, content):
    target = tmp_path / "config.json"
    target.write_text(content, encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat config.json")

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert result["output"] == ""


def test_git_remote_redacts_token_only_url_userinfo(tmp_path):
    (tmp_path / ".git").mkdir()
    navigator = make_navigator(tmp_path)
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0,
        stdout="origin https://singleparttoken@example.com/org/repo.git (fetch)",
        stderr="",
    )
    with patch(
        "app.adapters.infrastructure.secure_shell_navigation.subprocess.run",
        return_value=completed,
    ):
        result = navigator.execute("git remote -v")

    assert result["success"] is True
    assert "singleparttoken" not in result["output"]
    assert "[REDACTED]" in result["output"]


def test_git_rejects_same_line_executable_config_header(tmp_path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        '[filter "pwn"] clean = !whoami\n',
        encoding="utf-8",
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git diff --stat")

    assert result["success"] is False
    assert result["status"] == "git_config_rejected"
    run.assert_not_called()


def test_git_rejects_bom_prefixed_executable_config(tmp_path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        '\ufeff[core]\nfsmonitor = !whoami\n',
        encoding="utf-8",
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git status")

    assert result["success"] is False
    assert result["status"] == "git_config_rejected"
    run.assert_not_called()


def test_git_rejects_worktree_config_with_executable_helper(tmp_path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(
        '[extensions]\nworktreeConfig = true\n',
        encoding="utf-8",
    )
    (git_dir / "config.worktree").write_text(
        '[core]\nfsmonitor = !whoami\n',
        encoding="utf-8",
    )
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git status")

    assert result["success"] is False
    assert result["status"] == "git_config_rejected"
    run.assert_not_called()


def test_git_diff_rejects_filter_attributes(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitattributes").write_text("*.txt filter=pwn\n", encoding="utf-8")
    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory=repo)

    with patch("app.adapters.infrastructure.secure_shell_navigation.subprocess.run") as run:
        result = navigator.execute("git diff --stat")

    assert result["success"] is False
    assert result["status"] == "git_config_rejected"
    run.assert_not_called()


@pytest.mark.parametrize(
    "relative",
    (
        "AppData/Roaming/FileZilla/sitemanager.xml",
        "AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine/ConsoleHost_history.txt",
        ".terraform.d/credentials.tfrc.json",
    ),
)
def test_cat_blocks_additional_credential_stores(tmp_path, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("password=do-not-disclose", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cat "{relative}"')

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert result["output"] == ""
