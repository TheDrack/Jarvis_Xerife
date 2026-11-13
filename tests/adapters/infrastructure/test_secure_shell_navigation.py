from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from app.adapters.infrastructure.secure_shell_navigation import (
    ShellNavigator,
    _SECRET_CONTENT,
    register_shell_navigation_tools,
)
from app.adapters.infrastructure import session_authorization
from app.adapters.infrastructure.session_authorization import SessionAuthorizationGateway


class FakeMCP:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, *, name: str):
        def register(function):
            self.tools[name] = function
            return function

        return register


def make_navigator(root: Path, **kwargs) -> ShellNavigator:
    return ShellNavigator(
        allowed_roots=[root],
        initial_directory=root,
        **kwargs,
    )


def test_pwd_returns_the_current_allowed_directory(tmp_path):
    navigator = make_navigator(tmp_path)

    result = navigator.execute("pwd")

    assert result["success"] is True
    assert result["status"] == "ok"
    assert result["output"] == str(tmp_path.resolve())


def test_cd_changes_directory_and_pwd_observes_the_change(tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    navigator = make_navigator(tmp_path)

    changed = navigator.execute("cd child")
    observed = navigator.execute("pwd")

    assert changed["success"] is True
    assert changed["cwd"] == str(child.resolve())
    assert observed["output"] == str(child.resolve())


def test_cd_without_argument_returns_to_initial_directory(tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    navigator = make_navigator(tmp_path)

    navigator.execute("cd child")
    result = navigator.execute("cd")

    assert result["success"] is True
    assert result["cwd"] == str(tmp_path.resolve())


def test_cd_rejects_paths_outside_allowed_roots(tmp_path):
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cd "{outside}"')

    assert result["success"] is False
    assert result["status"] == "path_rejected"
    assert navigator.cwd == tmp_path.resolve()


def test_parent_traversal_is_rejected(tmp_path):
    navigator = make_navigator(tmp_path)

    result = navigator.execute("ls ../")

    assert result["success"] is False
    assert result["status"] == "path_rejected"


def test_ls_returns_bounded_metadata_without_file_contents(tmp_path):
    (tmp_path / "visible.txt").write_text("do not include file content", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    navigator = make_navigator(tmp_path, max_entries=10)

    result = navigator.execute("ls")

    assert result["success"] is True
    assert result["status"] == "listed"
    entries = {item["name"]: item for item in result["entries"]}
    assert entries["visible.txt"]["kind"] == "file"
    assert entries["folder"]["kind"] == "directory"
    assert "do not include file content" not in json.dumps(result)


def test_ls_caps_scandir_before_sorting(tmp_path):
    for index in range(30):
        (tmp_path / f"entry-{index:02d}.txt").touch()
    navigator = make_navigator(tmp_path, max_entries=3)

    result = navigator.execute("ls")

    assert result["success"] is True
    assert result["truncated"] is True
    assert len(result["entries"]) == 3


def test_ls_reports_but_does_not_follow_symlinks(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    link = tmp_path / "outside-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("ls")

    assert result["success"] is True
    entry = next(item for item in result["entries"] if item["name"] == "outside-link")
    assert entry["kind"] == "symlink"
    assert "secret.txt" not in json.dumps(result)


def test_cd_rejects_symlink_components(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cd link")

    assert result["success"] is False
    assert result["status"] == "path_rejected"
    assert navigator.cwd == tmp_path.resolve()


def test_cat_reads_bounded_utf8_text(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("first line\nsecond line\n", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat notes.txt")

    assert result["success"] is True
    assert result["status"] == "read"
    assert result["content"] == "first line\nsecond line\n"
    assert result["output"] == result["content"]


def test_cat_supports_quoted_paths_with_spaces(tmp_path):
    target = tmp_path / "notes with spaces.txt"
    target.write_text("hello\n", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute('cat "notes with spaces.txt"')

    assert result["success"] is True
    assert result["content"] == "hello\n"


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".netrc",
        ".npmrc",
        ".git-credentials",
        "id_rsa",
        "private.pem",
        "client.p12",
        "credentials.json",
    ],
)
def test_cat_blocks_sensitive_file_names(tmp_path, name):
    target = tmp_path / name
    target.write_text("ordinary text", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cat "{name}"')

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert result["content"] == ""


@pytest.mark.parametrize(
    "content",
    [
        "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwx\n",
        '{"tokenValue":"sensitive-value-with-spaces"}',
        "password: database-secret-value\n",
        "Authorization: Basic c2VjcmV0OnBhc3N3b3Jk\n",
        "<password>xml-secret-value</password>",
        "-----BEGIN PRIVATE KEY-----\nprivate-material\n",
    ],
)
def test_cat_blocks_credential_material_in_ordinary_named_files(tmp_path, content):
    target = tmp_path / "application-config.txt"
    target.write_text(content, encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat application-config.txt")

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert result["content"] == ""
    assert content not in json.dumps(result)


def test_cat_rejects_binary_content(tmp_path):
    target = tmp_path / "image.txt"
    target.write_bytes(b"header\x00binary")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat image.txt")

    assert result["success"] is False
    assert result["status"] == "binary_file"
    assert result["content"] == ""


def test_cat_drops_an_incomplete_final_line_when_byte_cap_is_reached(tmp_path):
    target = tmp_path / "config.txt"
    target.write_text("safe: yes\nPASSWORD=" + "x" * 500 + "\n", encoding="utf-8")
    navigator = make_navigator(tmp_path, max_read_bytes=32)

    result = navigator.execute("cat config.txt")

    assert result["success"] is True
    assert result["truncated"] is True
    assert result["content"] == "safe: yes\n"
    assert "PASSWORD" not in result["content"]


def test_shell_operators_are_rejected(tmp_path):
    navigator = make_navigator(tmp_path)

    for command in ("pwd; whoami", "ls | cat", "cat $(whoami)", "pwd\nwhoami"):
        result = navigator.execute(command)
        assert result["success"] is False
        assert result["status"] == "command_rejected"


def test_git_and_unknown_commands_are_rejected(tmp_path):
    navigator = make_navigator(tmp_path)

    for command in ("git status", "python -c print(1)", "whoami"):
        result = navigator.execute(command)
        assert result["success"] is False
        assert result["status"] == "command_rejected"


def test_command_length_is_bounded(tmp_path):
    navigator = make_navigator(tmp_path)

    result = navigator.execute("x" * 2049)

    assert result["success"] is False
    assert result["status"] == "command_rejected"


def test_shell_navigation_tool_is_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("JARVIS_SHELL_NAVIGATION_ENABLED", raising=False)
    mcp = FakeMCP()

    registered = register_shell_navigation_tools(mcp)

    assert registered == ()
    assert mcp.tools == {}


def test_shell_navigation_tool_registers_and_uses_injected_navigator(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SHELL_NAVIGATION_ENABLED", "1")
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    pairing = gateway.create_session(profile="observer")
    gateway.authenticate(pairing["pairing_code"])
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    mcp = FakeMCP()
    navigator = make_navigator(tmp_path)

    registered = register_shell_navigation_tools(mcp, navigator=navigator)
    result = mcp.tools["shell_navigate"]("pwd")

    assert registered == ("shell_navigate",)
    assert result["success"] is True
    assert result["output"] == str(tmp_path.resolve())
    assert result["session_id"] == pairing["session_id"]


def test_shell_navigation_tool_fails_closed_without_session(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SHELL_NAVIGATION_ENABLED", "1")
    gateway = SessionAuthorizationGateway(tmp_path / "session.json")
    monkeypatch.setattr(session_authorization, "SESSION_GATEWAY", gateway)
    mcp = FakeMCP()

    register_shell_navigation_tools(mcp, navigator=make_navigator(tmp_path))
    result = mcp.tools["shell_navigate"]("pwd")

    assert result["success"] is False
    assert result["status"] == "session_authorization_denied"


def test_parser_preserves_backslashes_in_quoted_windows_paths():
    slash = chr(92)
    windows_path = "C:" + slash + "Users" + slash + "Example" + slash + "notes.txt"
    command = 'cat "' + windows_path + '"'

    assert ShellNavigator._tokens(command) == ["cat", windows_path]


@pytest.mark.skipif(os.name != "nt", reason="Windows path aliases are platform-specific")
@pytest.mark.parametrize(
    "suffix",
    ["file:stream", "file.", "file ", "COM1", "NUL.txt", "COM¹", "LPT².txt"],
)
def test_windows_device_and_stream_aliases_are_rejected(tmp_path, suffix):
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cat "{suffix}"')

    assert result["success"] is False
    assert result["status"] == "path_rejected"


@pytest.mark.parametrize(
    "content",
    [
        "key: base64-private-material-value\nmode: safe\n",
        '{"key":"generic secret material with spaces"}',
        "Authorization: Bearer opaque-access-token-value\n",
        'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue123456789',
        "password: |\n  first-line-secret-material\n  second-line-secret-material\nmode: safe\n",
    ],
)
def test_cat_blocks_generic_key_bearer_and_yaml_block_secrets(tmp_path, content):
    target = tmp_path / "ordinary-config.yaml"
    target.write_text(content, encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat ordinary-config.yaml")

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert result["content"] == ""
    assert content not in json.dumps(result)


def test_cat_blocks_git_metadata_directory(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\nurl = https://user:token@example.invalid/repo.git\n',
        encoding="utf-8",
    )
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat .git/config")

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert result["content"] == ""


def test_relative_initial_directory_is_resolved_from_first_allowed_root(tmp_path):
    child = tmp_path / "workspace"
    child.mkdir()

    navigator = ShellNavigator(allowed_roots=[tmp_path], initial_directory="workspace")

    assert navigator.cwd == child.resolve()
    assert navigator.execute("pwd")["output"] == str(child.resolve())

@pytest.mark.parametrize(
    "filename",
    ["kubeconfig.yaml", "netrc.txt", "pgpass.txt", "htpasswd.txt", "terraform.tfstate.json"],
)
def test_cat_blocks_credential_store_filename_variants(tmp_path, filename):
    target = tmp_path / filename
    target.write_text("ordinary-looking content", encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute(f'cat "{filename}"')

    assert result["success"] is False
    assert result["status"] == "sensitive_file_blocked"
    assert result["content"] == ""


@pytest.mark.parametrize(
    "content",
    [
        "client-key-data: " + "A" * 48,
        "bindpw: directory-secret-value",
        "SMTP_PASS=mail-secret-value",
        "DATABASE_URL=postgresql://user:secret-value@db.internal/app",
        "hvs." + "a" * 24,
        "sk_live_" + "b" * 24,
        "INSERT INTO users (password) VALUES ('sql-secret-value');",
        "password: |\n  first-line-secret-material\n  second-line-secret-material\nmode: safe\n",
    ],
)
def test_cat_blocks_additional_credential_shapes(tmp_path, content):
    target = tmp_path / "ordinary-config.yaml"
    target.write_text(content, encoding="utf-8")
    navigator = make_navigator(tmp_path)

    result = navigator.execute("cat ordinary-config.yaml")

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert result["content"] == ""
    assert content not in json.dumps(result)


def test_secret_scanner_handles_maximum_whitespace_input_without_cross_line_backtracking():
    assert _SECRET_CONTENT.search(b"\n" * (64 * 1024)) is None

def test_blocked_file_read_does_not_hold_the_navigator_lock(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("safe content\\n", encoding="utf-8")
    navigator = make_navigator(tmp_path)
    read_started = threading.Event()
    release_read = threading.Event()
    pwd_finished = threading.Event()
    pwd_result = {}

    original_read = navigator._read_text

    def blocked_read(raw_path, *, base=None):
        read_started.set()
        assert release_read.wait(2)
        return original_read(raw_path, base=base)

    monkeypatch.setattr(navigator, "_read_text", blocked_read)
    read_thread = threading.Thread(target=lambda: navigator.execute("cat notes.txt"))
    read_thread.start()
    assert read_started.wait(1)

    def read_pwd():
        pwd_result.update(navigator.execute("pwd"))
        pwd_finished.set()

    pwd_thread = threading.Thread(target=read_pwd)
    pwd_thread.start()
    completed_without_waiting_for_io = pwd_finished.wait(0.25)
    release_read.set()
    read_thread.join(1)
    pwd_thread.join(1)

    assert completed_without_waiting_for_io is True
    assert pwd_result["success"] is True
    assert not read_thread.is_alive()
    assert not pwd_thread.is_alive()

