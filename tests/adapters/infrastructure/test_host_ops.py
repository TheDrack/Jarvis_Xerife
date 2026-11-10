"""Unit tests for the read-only host operations policy."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from app.adapters.infrastructure import host_ops as ops


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """Keep every path, audit write and secret fixture inside tmp_path."""
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", str(tmp_path))
    monkeypatch.setenv("JARVIS_HOST_OPS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #
def test_list_returns_metadata_and_filters_credentials(_sandbox):
    (_sandbox / "notes.txt").write_text("hello", encoding="utf-8")
    (_sandbox / "sub").mkdir()
    (_sandbox / ".env").write_text("OPENAI_API_KEY=sk-should-never-be-listed", encoding="utf-8")
    (_sandbox / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")

    result = ops.list_directory(str(_sandbox), depth=1, max_entries=50)

    names = {entry["name"] for entry in result["entries"]}
    assert result["success"] is True
    assert result["status"] == "listed"
    assert {"notes.txt", "sub"}.issubset(names)
    assert ".env" not in names
    assert "id_rsa" not in names
    assert result["filtered_secret_entries"] == 2
    assert result["followed_symlinks"] is False
    note = next(entry for entry in result["entries"] if entry["name"] == "notes.txt")
    assert note["kind"] == "file"
    assert note["size"] == 5


def test_list_honours_depth_and_entry_cap(_sandbox):
    nested = _sandbox / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "deep.txt").write_text("x", encoding="utf-8")

    shallow = ops.list_directory(str(_sandbox), depth=1, max_entries=100)
    assert "deep.txt" not in {entry["name"] for entry in shallow["entries"]}

    capped = ops.list_directory(str(_sandbox), depth=4, max_entries=2)
    assert len(capped["entries"]) == 2
    assert capped["truncated"] is True


@pytest.mark.parametrize("path", ["..", "../", "sub/../../", "." + os.sep + ".."])
def test_list_rejects_parent_traversal(path):
    with pytest.raises(ops.PathNotAllowed):
        ops.list_directory(path)


def test_list_rejects_paths_outside_allowed_roots(_sandbox):
    with pytest.raises(ops.PathNotAllowed):
        ops.list_directory(str(Path(_sandbox.anchor)))


@pytest.mark.parametrize(
    "depth,max_entries", [(5, 10), (-1, 10), (1, 0), (1, 501), (True, 10)]
)
def test_list_rejects_out_of_range_limits(depth, max_entries):
    with pytest.raises(ValueError):
        ops.list_directory(".", depth=depth, max_entries=max_entries)


def test_symlink_cannot_escape_an_allowed_root(_sandbox):
    outside = Path(os.environ.get("SystemRoot") or "/etc")
    link = _sandbox / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privileges on this host")

    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path(str(link))


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", [".env", ".env.production", "server.pem", "id_ed25519", ".npmrc"])
def test_read_blocks_credential_file_names(_sandbox, name):
    target = _sandbox / name
    target.write_text("value=1", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.read_text_file(str(target))


def test_read_blocks_private_key_material(_sandbox):
    target = _sandbox / "notes.txt"
    target.write_text(
        "line\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target))

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert "content" not in result


def test_read_redacts_tokens_and_reports_replacements(_sandbox):
    target = _sandbox / "config.txt"
    target.write_text(
        'api_key = "super-secret-value-123"\ntoken: sk-abcdefghijklmnopqrstuvwx\n',
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target))

    assert result["success"] is True
    assert result["redactions"] >= 2
    assert "super-secret-value-123" not in result["content"]
    assert "sk-abcdefghijklmnopqrstuvwx" not in result["content"]
    assert "[REDACTED" in result["content"]


def test_read_enforces_byte_and_line_limits(_sandbox):
    target = _sandbox / "big.txt"
    target.write_text("x" * 5000 + "\n" + "\n".join("line" for _ in range(20)), encoding="utf-8")

    by_bytes = ops.read_text_file(str(target), max_bytes=100, max_lines=4000)
    by_lines = ops.read_text_file(str(target), max_bytes=262144, max_lines=3)

    assert by_bytes["truncated"] is True
    assert by_bytes["bytes_returned"] <= 100
    assert by_lines["lines_returned"] == 3
    assert by_lines["truncated"] is True


def test_read_refuses_binary_content(_sandbox):
    target = _sandbox / "blob.bin"
    target.write_bytes(b"abc\x00def")

    result = ops.read_text_file(str(target))

    assert result["success"] is False
    assert result["status"] == "binary_file"


def test_read_validates_limits(_sandbox):
    target = _sandbox / "a.txt"
    target.write_text("a", encoding="utf-8")

    with pytest.raises(ValueError):
        ops.read_text_file(str(target), max_bytes=0)
    with pytest.raises(ValueError):
        ops.read_text_file(str(target), max_lines=4001)


# --------------------------------------------------------------------------- #
# Command compilation
# --------------------------------------------------------------------------- #
@pytest.fixture
def _fake_powershell(monkeypatch):
    monkeypatch.setattr(ops, "_powershell_executable", lambda: "powershell.exe")


def test_git_profile_builds_structured_argv(_fake_powershell):
    compiled = ops.compile_command("git", "status", ["--short"])

    assert compiled.argv == ("git", "--no-pager", "status", "--short")
    assert compiled.timeout_seconds == 20
    assert compiled.display == "status --short"


@pytest.mark.parametrize(
    "verb,arguments",
    [
        ("push", []),
        ("config", ["user.name"]),
        ("log", ["-C", "C:/Windows"]),
        ("log", ["--git-dir=C:/evil"]),
    ],
)
def test_git_rejects_unlisted_or_relocating_commands(verb, arguments):
    with pytest.raises(ValueError):
        ops.compile_command("git", verb, arguments)


def test_powershell_rejects_shell_injection_and_unlisted_parameters(_fake_powershell):
    with pytest.raises((PermissionError, ValueError)):
        ops.compile_command(
            "powershell_readonly", "Get-ChildItem", ["-Path", "C:/tmp; Remove-Item C:/tmp"]
        )
    with pytest.raises(ValueError):
        ops.compile_command("powershell_readonly", "Get-ChildItem", ["-Filter", "*.py", "-Recurse"])
    with pytest.raises((PermissionError, ValueError)):
        ops.compile_command("powershell_readonly", "Invoke-Expression", ["Get-Date"])


def test_powershell_rejects_paths_outside_allowed_roots(_fake_powershell):
    with pytest.raises(ops.PathNotAllowed):
        ops.compile_command("powershell_readonly", "Get-Item", ["-Path", "C:/Windows"])


@pytest.mark.parametrize(
    "verb,arguments",
    [
        ("Remove-Item", ["C:/tmp/x"]),
        ("Set-ItemProperty", ["-Path", "HKLM:/x"]),
        ("Start-Process", ["powershell.exe"]),
        ("Stop-Service", ["-Name", "Tailscale"]),
        ("New-Item", ["-Path", "C:/x"]),
    ],
)
def test_destructive_and_privileged_verbs_are_hard_blocked(verb, arguments):
    with pytest.raises(PermissionError):
        ops.compile_command("powershell_readonly", verb, arguments)


def test_pytest_profile_requires_targets_under_tests():
    with pytest.raises(ops.PathNotAllowed):
        ops.compile_command("pytest", "run", ["app/adapters/infrastructure/host_ops.py"])
    with pytest.raises(ValueError):
        ops.compile_command("pytest", "run", ["tests", "-p", "evil_plugin"])


def test_pytest_profile_compiles_without_a_shell():
    compiled = ops.compile_command(
        "pytest", "run", ["tests/adapters/infrastructure/test_host_ops.py", "-x"]
    )

    assert compiled.argv[1:3] == ("-m", "pytest")
    assert "--no-cov" in compiled.argv
    assert "-p" in compiled.argv and "no:cacheprovider" in compiled.argv


@pytest.mark.skipif(os.name != "nt", reason="D:\\ inspection is Windows-only")
def test_inspect_d_profile_confines_paths_to_d_drive(
    _fake_powershell, monkeypatch, tmp_path
):
    monkeypatch.setenv(
        "JARVIS_HOST_OPS_ROOTS", os.pathsep.join([str(tmp_path), "D:/"])
    )
    with pytest.raises(ops.PathNotAllowed):
        ops.compile_command("inspect_d", "Get-ChildItem", ["-Path", "C:/Windows"])
    compiled = ops.compile_command("inspect_d", "Get-ChildItem", ["-Path", "D:/", "-Depth", "1"])
    assert "'D:\\'" in compiled.argv[-1] or "'D:/'" in compiled.argv[-1]


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        ops.compile_command("bash", "ls", [])


@pytest.mark.parametrize("timeout", [0, 61, True])
def test_timeout_bounds_are_enforced(timeout):
    with pytest.raises(ValueError):
        ops.compile_command("git", "status", [], timeout_seconds=timeout)


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def _stub_spawn(stdout="ok", stderr="", code=0, capture=None):
    def spawn(argv, cwd, environment, timeout_seconds):
        if capture is not None:
            capture.update(
                {"argv": list(argv), "cwd": cwd, "env": dict(environment), "timeout": timeout_seconds}
            )
        return subprocess.CompletedProcess(list(argv), code, stdout, stderr)

    return spawn


def test_run_uses_argv_without_shell_and_sanitizes_environment(monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "must-not-be-forwarded")
    capture: dict = {}
    monkeypatch.setattr(ops, "_spawn", _stub_spawn(capture=capture))

    result = ops.run_host_command("git", "status", ["--short"], timeout_seconds=9)

    assert result["success"] is True
    assert result["shell"] is False
    assert result["elevated"] is False
    assert capture["argv"][:3] == ["git", "--no-pager", "status"]
    assert capture["timeout"] == 9
    assert "SECRET_TOKEN" not in capture["env"]
    assert capture["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_run_truncates_and_redacts_output(monkeypatch):
    payload = '{"token":"sk-abcdefghijklmnopqrstuvwx"}' + ("x" * 20000)
    monkeypatch.setattr(ops, "_spawn", _stub_spawn(stdout=payload, stderr="boom"))

    result = ops.run_host_command("git", "status", [])

    assert result["truncated"] is True
    assert len(result["stdout"]) <= ops.MAX_STDOUT_CHARS
    assert "sk-abcdefghijklmnopqrstuvwx" not in result["stdout"]
    assert "[REDACTED" in result["stdout"]
    assert result["stderr"] == "boom"


def test_run_returns_a_bounded_timeout_result(monkeypatch):
    def spawn(argv, cwd, environment, timeout_seconds):
        raise subprocess.TimeoutExpired(argv, timeout_seconds, output="partial", stderr="")

    monkeypatch.setattr(ops, "_spawn", spawn)

    result = ops.run_host_command("git", "status", [], timeout_seconds=2)

    assert result["status"] == "timeout"
    assert result["timed_out"] is True
    assert result["stdout"] == "partial"


def test_blocked_command_is_audited_and_never_spawned(monkeypatch):
    spawned = {"called": False}

    def spawn(*args, **kwargs):  # pragma: no cover - must not run
        spawned["called"] = True
        raise AssertionError("blocked command must not spawn")

    monkeypatch.setattr(ops, "_spawn", spawn)

    result = ops.run_host_command("powershell_readonly", "Remove-Item", ["-Path", "C:/x"])

    assert result["status"] == "operation_blocked"
    assert result["audit_logged"] is True
    assert spawned["called"] is False
    records = [
        json.loads(line)
        for line in (_sandbox_audit()).read_text(encoding="utf-8").splitlines()
    ]
    assert records[-1]["event"] == "blocked"
    assert records[-1]["elevated"] is False


def _sandbox_audit() -> Path:
    return Path(os.environ["JARVIS_HOST_OPS_AUDIT_LOG"])


def test_execution_is_audited_without_output_content(monkeypatch):
    monkeypatch.setattr(ops, "_spawn", _stub_spawn(stdout="secret-ish stdout", code=0))

    result = ops.run_host_command("git", "log", ["-n", "2"])

    assert result["success"] is True
    record = json.loads(_sandbox_audit().read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "executed"
    assert record["audit_id"] == result["audit_id"]
    assert "stdout" not in record
    assert record["exit_code"] == 0


# --------------------------------------------------------------------------- #
# Confirmation gate
# --------------------------------------------------------------------------- #
def test_read_only_capability_needs_no_confirmation():
    result = ops.request_confirmation("git", "status")

    assert result["success"] is False
    assert result["status"] == "confirmation_not_applicable"


def test_confirmation_token_is_bound_single_use_and_required(monkeypatch):
    monkeypatch.setattr(ops, "_CONFIRMABLE_PROFILES", frozenset({"git"}))
    monkeypatch.setattr(ops, "_spawn", _stub_spawn())
    issued = ops.request_confirmation("git", "status", ["--short"])
    assert issued["status"] == "confirmation_required"

    missing = ops.run_host_command("git", "status", ["--short"])
    assert missing["status"] == "confirmation_required"

    wrong_scope = ops.run_host_command("git", "status", [], confirm_token=issued["token"])
    assert wrong_scope["status"] == "confirmation_required"

    accepted = ops.run_host_command(
        "git", "status", ["--short"], confirm_token=issued["token"]
    )
    assert accepted["success"] is True

    replay = ops.run_host_command(
        "git", "status", ["--short"], confirm_token=issued["token"]
    )
    assert replay["status"] == "confirmation_required"


def test_confirmation_never_unlocks_a_blocked_operation(monkeypatch):
    monkeypatch.setattr(ops, "_CONFIRMABLE_PROFILES", frozenset({"powershell_readonly"}))

    result = ops.run_host_command("powershell_readonly", "Remove-Item", ["-Path", "C:/x"])

    assert result["status"] == "operation_blocked"


def test_describe_profiles_reports_boundaries(_sandbox):
    description = ops.describe_profiles()

    assert description["read_only"] is True
    assert {profile["name"] for profile in description["profiles"]} == set(ops.PROFILES)
    assert description["confirmable_profiles"] == []
    assert "filesystem writes" in description["blocked_capabilities"]
    assert any(Path(root) == _sandbox.resolve() for root in description["roots"])
