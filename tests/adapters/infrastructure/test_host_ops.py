"""Unit tests for the read-only host operations policy."""
from __future__ import annotations

import json
import os
import subprocess
import sys
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
        'api_key = "ordinary-secret-value-123"\ntoken: ordinary-token-value-123\n',
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target))

    assert result["success"] is True
    assert result["redactions"] >= 2
    assert "ordinary-secret-value-123" not in result["content"]
    assert "ordinary-token-value-123" not in result["content"]
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

    assert compiled.argv == (
        "git",
        "-c", "core.fsmonitor=false",
        "-c", "core.untrackedCache=false",
        "-c", f"core.hooksPath={os.devnull}",
        "-c", f"core.sshCommand={os.devnull}",
        "-c", "diff.external=",
        "-c", "core.pager=cat",
        "-c", f"core.attributesFile={os.devnull}",
        "-c", "log.showSignature=false",
        "--no-pager",
        "status",
        "--short",
    )
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


@pytest.mark.parametrize("profile", ["bash", "pytest"])
def test_unknown_profile_is_rejected(profile):
    with pytest.raises(ValueError):
        ops.compile_command(profile, "ls", [])


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
    assert capture["argv"][:2] == ["git", "-c"]
    assert "core.fsmonitor=false" in capture["argv"]
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
    assert "arguments" not in record
    assert "argument_digest" in record
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


# --------------------------------------------------------------------------- #
# Security review regressions: Strix findings
# --------------------------------------------------------------------------- #
def test_list_filters_credential_directories(_sandbox):
    for name in (".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".password-store", ".terraform", ".vault"):
        (_sandbox / name).mkdir()
    (_sandbox / "project").mkdir()

    result = ops.list_directory(str(_sandbox), depth=1, max_entries=100)

    names = {entry["name"] for entry in result["entries"]}
    assert names == {"project"}
    assert result["filtered_secret_entries"] == 9


@pytest.mark.parametrize(
    "provider_path",
    [
        "Registry::HKEY_LOCAL_MACHINE\\Software",
        "FileSystem::C:/Windows",
        "Env:PATH",
        "Variable:HOME",
        "Cert:\\CurrentUser\\My",
    ],
)
def test_powershell_path_arguments_reject_non_filesystem_providers(provider_path):
    with pytest.raises((ValueError, ops.PathNotAllowed)):
        ops.compile_command(
            "powershell_readonly", "Get-ChildItem", ["-Path", provider_path]
        )


def test_git_show_and_diff_require_metadata_only_output():
    with pytest.raises(ValueError):
        ops.compile_command("git", "show", ["HEAD"])
    with pytest.raises(ValueError):
        ops.compile_command("git", "diff", [])

    assert "--stat" in ops.compile_command("git", "show", ["--stat", "HEAD"]).argv
    assert "--name-only" in ops.compile_command("git", "diff", ["--name-only"]).argv


def test_redaction_covers_provider_qualified_secret_environment_names():
    payload = (
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnop "
        "SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiJ9 "
        "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE "
        "DATABASE_URL=postgresql://user:supersecret@db.example.test/app"
    )

    sanitized, count = ops.redact(payload)

    assert count >= 4
    assert "sk-proj-abcdefghijklmnop" not in sanitized
    assert "eyJhbGciOiJIUzI1NiJ9" not in sanitized
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "supersecret" not in sanitized


@pytest.mark.parametrize("name", ["prod.env", "kubeconfig", "admin.conf", "prod.tfvars", "terraform.tfstate"])
def test_read_blocks_additional_credential_and_state_file_names(_sandbox, name):
    target = _sandbox / name
    target.write_text("credential=value", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.read_text_file(str(target))


@pytest.mark.parametrize(
    "provider_path",
    [
        "Env:PATH",
        "Variable:HOME",
        "Cert:\\CurrentUser\\My",
        "HKCU:\\Software",
        "Registry::HKEY_LOCAL_MACHINE\\Software",
        "FileSystem::C:\\Windows",
        "D:",
    ],
)
def test_shared_path_resolver_rejects_provider_and_drive_relative_paths(provider_path):
    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path(provider_path)


def test_listing_secret_directory_directly_is_blocked(_sandbox):
    ssh = _sandbox / ".ssh"
    ssh.mkdir()
    (ssh / "known_hosts").write_text("host-key", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.list_directory(str(ssh))


def test_redaction_covers_common_provider_secrets_and_connection_urls():
    payload = (
        "AWS_SECRET_ACCESS_KEY=aws-secret-value "
        "SECRET_KEY=secret-key-value "
        "SERVICE_TOKEN=service-token-value "
        "client-key-data: BASE64PRIVATEKEYMATERIAL "
        "certificate-authority-data: BASE64CERTDATA "
        "postgres://user:dbpassword@db.example.test/app "
        "redis://:redispassword@cache.example.test/0 "
        "github_pat_abcdefghijklmnopqrstuvwxyz123456"
    )

    sanitized, count = ops.redact(payload)

    assert count >= 8
    for secret in (
        "aws-secret-value", "secret-key-value", "service-token-value",
        "BASE64PRIVATEKEYMATERIAL", "BASE64CERTDATA", "dbpassword",
        "redispassword", "github_pat_abcdefghijklmnopqrstuvwxyz123456",
    ):
        assert secret not in sanitized


def test_command_output_with_private_key_material_is_withheld(monkeypatch):
    private_key = "PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    monkeypatch.setattr(ops, "_spawn", _stub_spawn(stdout=private_key, stderr=private_key))

    result = ops.run_host_command("git", "status", [])

    assert result["success"] is True
    assert "MIIEowIBAAKCAQEA" not in result["stdout"]
    assert "MIIEowIBAAKCAQEA" not in result["stderr"]
    assert result["stdout"].startswith("[WITHHELD:")
    assert result["stderr"].startswith("[WITHHELD:")


def test_inspect_d_profile_does_not_expose_other_drive_metadata():
    with pytest.raises(ValueError):
        ops.compile_command("inspect_d", "Get-PSDrive", ["-Name", "C"])


def test_git_profile_disables_repository_config_execution_surfaces():
    compiled = ops.compile_command("git", "status", [])
    argv_pairs = set(zip(compiled.argv[1::2], compiled.argv[2::2]))

    assert ("-c", "core.fsmonitor=false") in argv_pairs
    assert ("-c", "core.untrackedCache=false") in argv_pairs
    assert ("-c", f"core.hooksPath={os.devnull}") in argv_pairs
    assert ("-c", "diff.external=") in argv_pairs
    assert ("-c", "core.pager=cat") in argv_pairs
    assert ("-c", f"core.attributesFile={os.devnull}") in argv_pairs
    assert ("-c", "log.showSignature=false") in argv_pairs
    assert "--no-pager" in compiled.argv


@pytest.mark.parametrize(
    "config",
    [
        '[filter "evil"]\n    clean = cmd /c whoami\n',
        '[core]\n    sshCommand = cmd /c whoami\n',
        '[core]\n    worktree = C:/outside\n',
        '[include]\n    path = C:/outside/config\n',
        '[diff "evil"]\n    textconv = cmd /c whoami\n',
    ],
)
def test_git_profile_rejects_repository_config_with_execution_or_worktree_overrides(tmp_path, config):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match="repository config contains"):
        ops._reject_repository_execution_config(tmp_path)


def test_git_profile_allows_inert_repository_config(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        '[core]\n    repositoryformatversion = 0\n    filemode = true\n',
        encoding="utf-8",
    )

    ops._reject_repository_execution_config(tmp_path)


def test_git_environment_disables_lazy_fetch():
    assert ops._sanitized_environment()["GIT_NO_LAZY_FETCH"] == "1"


def test_git_commit_probe_uses_the_same_safety_overrides(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(ops.subprocess, "run", fake_run)
    ops._require_commitish("HEAD", ops._repository_root())

    assert ("-c", "core.fsmonitor=false") in set(zip(captured["argv"][1::2], captured["argv"][2::2]))
    assert ("-c", f"core.hooksPath={os.devnull}") in set(zip(captured["argv"][1::2], captured["argv"][2::2]))
    assert ("-c", "diff.external=") in set(zip(captured["argv"][1::2], captured["argv"][2::2]))


def test_git_environment_ignores_user_and_system_configuration():
    environment = ops._sanitized_environment()

    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert environment["GIT_ATTR_NOSYSTEM"] == "1"


@pytest.mark.parametrize(
    "name",
    [
        ".pgpass", "pgpass.conf", "client_secret.json",
        "application_default_credentials.json", ".htpasswd",
        "server.ppk", "server.asc", "client.ovpn", "terraform.tfstate.backup",
    ],
)
def test_read_blocks_additional_credential_store_names(_sandbox, name):
    target = _sandbox / name
    target.write_text("credential=value", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.read_text_file(str(target))


@pytest.mark.parametrize(
    "private_material",
    [
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\nprivate-data\n-----END PGP PRIVATE KEY BLOCK-----",
        "PuTTY-User-Key-File-2: ssh-ed25519\nPrivate-Lines: 1\nprivate-data",
        "-----BEGIN OpenVPN Static key V1-----\nprivate-data\n-----END OpenVPN Static key V1-----",
    ],
)
def test_read_blocks_non_pem_private_key_formats(_sandbox, private_material):
    target = _sandbox / "ordinary-notes.txt"
    target.write_text(private_material, encoding="utf-8")

    result = ops.read_text_file(str(target))

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert "content" not in result


def test_audit_does_not_persist_caller_supplied_secret_arguments(_fake_powershell, monkeypatch):
    # This test verifies audit redaction, not host PowerShell availability.
    monkeypatch.setattr(ops, "_spawn", _stub_spawn())
    secret = "AKIAIOSFODNN7EXAMPLE"
    result = ops.run_host_command(
        "powershell_readonly", "Get-ChildItem", ["-Filter", f"token={secret}"]
    )

    assert result["success"] is True
    audit = _sandbox_audit().read_text(encoding="utf-8")
    assert secret not in audit
    record = json.loads(audit.splitlines()[-1])
    assert "arguments" not in record
    assert record["argument_count"] == 2
    assert record["argument_digest"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows ACLs")
def test_audit_file_is_owner_only(_sandbox):
    ops._audit({"event": "permission-test"})
    mode = _sandbox_audit().stat().st_mode & 0o777

    assert mode == 0o600


@pytest.mark.parametrize(
    "network_path",
    [
        r"\\attacker.example\share\secret.txt",
        "//attacker.example/share/secret.txt",
        r"\\?\UNC\attacker.example\share\secret.txt",
        r"\\.\C$\Windows\win.ini",
    ],
)
def test_resolve_path_rejects_unc_and_device_paths_before_resolution(network_path):
    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path(network_path)


def test_allowed_roots_rejects_unc_configuration_before_resolution(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_OPS_ROOTS", r"\\attacker.example\share")

    with pytest.raises(ops.PathNotAllowed):
        ops.allowed_roots()


def test_powershell_cwd_cannot_rebase_relative_path_validation(_sandbox, _fake_powershell):
    alternate = _sandbox / "alternate-working-directory"
    alternate.mkdir()

    with pytest.raises(ops.PathNotAllowed):
        ops.compile_command(
            "powershell_readonly", "Get-ChildItem", ["-Path", "."], cwd=str(alternate)
        )


def test_entry_kind_detects_ntfs_junction_without_python_312_api(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delattr(ops.os.path, "isjunction", raising=False)
    entry = SimpleNamespace(
        path="C:\\junction",
        is_symlink=lambda: False,
        stat=lambda **kwargs: SimpleNamespace(st_file_attributes=0x400),
        is_dir=lambda **kwargs: True,
        is_file=lambda **kwargs: False,
    )

    assert ops._entry_kind(entry) == "junction"


def test_resolve_path_rejects_symlink_components_before_following_them(_sandbox):
    outside = _sandbox.parent / "outside-link-target"
    outside.mkdir()
    link = _sandbox / "link-to-outside"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privileges on this host")

    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path(str(link / "secret.txt"))


def test_directory_listing_never_follows_nested_symlinks(_sandbox):
    outside = _sandbox.parent / "outside-list-target"
    outside.mkdir()
    (outside / "outside-secret.txt").write_text("not-listed", encoding="utf-8")
    link = _sandbox / "external-link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation requires privileges on this host")

    result = ops.list_directory(str(_sandbox), depth=4, max_entries=100)

    linked = next(entry for entry in result["entries"] if entry["name"] == "external-link")
    assert linked["kind"] == "symlink"
    assert "outside-secret.txt" not in {entry["name"] for entry in result["entries"]}


def test_read_redacts_json_quoted_credential_keys(_sandbox):
    target = _sandbox / "appsettings.json"
    target.write_text(
        '{"OpenAI_API_Key":"json-secret-value","bot_token":"bot-secret-value","client-key-data":"base64-certificate-secret"}',
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target))

    assert result["success"] is True
    assert "json-secret-value" not in result["content"]
    assert "bot-secret-value" not in result["content"]
    assert "base64-certificate-secret" not in result["content"]
    assert result["redactions"] >= 3


@pytest.mark.parametrize(
    "name",
    [".envrc", "_netrc", "credential.json", ".pgpass.bak", "prod-secrets.yaml",
     "kubeconfig-prod.yaml", "credentials.json.bak"],
)
def test_read_blocks_additional_credential_filenames(_sandbox, name):
    target = _sandbox / name
    target.write_text("password=must-not-leak", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.read_text_file(str(target))


def test_mixed_separator_unc_is_rejected_before_resolution(_sandbox, monkeypatch):
    original = Path.resolve

    def guarded_resolve(path, *args, **kwargs):
        if str(path).replace("/", "\\\\").startswith("\\\\\\\\"):
            raise AssertionError("UNC path resolution must not be attempted")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path("\\\\attacker.example/share/secret.txt")


def test_git_profile_rejects_working_directory_outside_repository(tmp_path):
    outside = tmp_path / "other-repository"
    outside.mkdir()

    with pytest.raises(ops.PathNotAllowed):
        ops.compile_command("git", "status", [], cwd=str(outside))


def test_bound_redacts_sensitive_credential_names():
    value = r"Directory: C:\\Users\\operator\\.aws\\credentials.json"
    bounded, _ = ops._bound(value, 4000)

    assert ".aws" not in bounded
    assert "credentials.json" not in bounded
    assert "[REDACTED_NAME]" in bounded


def test_audit_redacts_unrecognized_profile_and_verb_labels(_sandbox):
    secret = "AWS_SECRET_ACCESS_KEY=must-not-persist"
    result = ops.run_host_command(secret, secret, ["ordinary-argument"])

    assert result["success"] is False
    audit = _sandbox_audit().read_text(encoding="utf-8")
    assert secret not in audit
    record = json.loads(audit.splitlines()[-1])
    assert record["profile"] == "unknown"
    assert record["verb"] == "unknown"


def test_junction_detection_uses_windows_reparse_attribute(monkeypatch):
    from types import SimpleNamespace
    import sys

    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(
            kernel32=SimpleNamespace(GetFileAttributesW=lambda _path: 0x400)
        ),
        c_wchar_p=lambda value: value,
    )
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    entry = SimpleNamespace(path="C:/safe/junction", is_symlink=lambda: False)

    assert ops._is_junction(entry) is True


def test_git_show_rejects_blob_object_targets(_sandbox, monkeypatch):
    monkeypatch.setattr(ops, "_repository_root", lambda: _sandbox)
    monkeypatch.setattr(ops, "allowed_roots", lambda: (_sandbox,))
    monkeypatch.setattr(
        ops.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr=""),
    )

    with pytest.raises(ValueError, match="commit"):
        ops.compile_command(
            "git", "show", ["--stat", "deadbeef"], cwd=str(_sandbox)
        )


def test_git_show_accepts_commit_object_targets(_sandbox, monkeypatch):
    monkeypatch.setattr(ops, "_repository_root", lambda: _sandbox)
    monkeypatch.setattr(ops, "allowed_roots", lambda: (_sandbox,))
    monkeypatch.setattr(
        ops.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="deadbeef", stderr=""),
    )

    compiled = ops.compile_command(
        "git", "show", ["--stat", "deadbeef"], cwd=str(_sandbox)
    )

    assert compiled.argv[0] == "git"
    assert "show" in compiled.argv


def test_bound_removes_credential_names_from_command_output():
    output = (
        "Directory: C:\\Users\\operator\\project\n"
        "d----- .ssh\n"
        "-a---- .env\n"
        "-a---- id_rsa\n"
        "-a---- credentials.json\n"
        "-a---- README.md\n"
    )

    bounded, _ = ops._bound(output, 4000)

    assert ".ssh" not in bounded
    assert ".env" not in bounded
    assert "id_rsa" not in bounded
    assert "credentials.json" not in bounded
    assert "README.md" in bounded


def test_audit_does_not_persist_rejected_credential_argument(_sandbox):
    secret = "AWS_SECRET_ACCESS_KEY=caller-supplied-secret"
    result = ops.run_host_command(
        "powershell_readonly", "Get-ChildItem", [secret]
    )

    assert result["success"] is False
    audit = _sandbox_audit().read_text(encoding="utf-8")
    assert secret not in audit


@pytest.mark.parametrize(
    "relative",
    [
        ".config/gh/hosts.yml",
        ".config/glab-cli/config.yml",
        ".config/github-copilot/hosts.json",
        ".config/composer/auth.json",
        ".config/containers/auth.json",
        ".config/age/keys.txt",
        ".config/ngrok/ngrok.yml",
        ".m2/settings.xml",
        ".yarnrc.yml",
    ],
)
def test_read_blocks_common_developer_credential_stores(_sandbox, relative):
    target = _sandbox / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("oauth_token: must-not-leak", encoding="utf-8")

    with pytest.raises(ops.PathNotAllowed):
        ops.read_text_file(str(target))


def test_read_blocks_xml_password_content_in_ordinary_config_file(_sandbox):
    target = _sandbox / "settings.xml"
    target.write_text(
        "<settings><servers><server><password>xml-secret-value</password></server></servers></settings>",
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target))

    assert result["success"] is False
    assert result["status"] == "secret_content_blocked"
    assert "xml-secret-value" not in result.get("content", "")


def test_directory_listing_bounds_scandir_before_sorting(_sandbox, monkeypatch):
    for index in range(30):
        (_sandbox / f"entry-{index:02d}.txt").write_text("x", encoding="utf-8")

    original_scandir = os.scandir
    observed = {"count": 0}

    def bounded_scandir(path):
        for entry in original_scandir(path):
            observed["count"] += 1
            yield entry
            if observed["count"] >= 4:
                break

    monkeypatch.setattr(ops.os, "scandir", bounded_scandir)
    result = ops.list_directory(str(_sandbox), max_entries=3)

    assert result["truncated"] is True
    assert result["entry_count"] == 3
    assert observed["count"] == 4


def test_git_show_and_diff_are_metadata_only():
    for verb, arguments in (
        ("show", ["--stat", "HEAD"]),
        ("diff", ["--name-only", "HEAD", "HEAD~1"]),
    ):
        compiled = ops.compile_command("git", verb, arguments)
        assert "--no-ext-diff" in compiled.argv
        assert "--no-textconv" in compiled.argv



@pytest.mark.skipif(os.name == "nt", reason="backslash is a path separator on Windows")
def test_allowed_root_with_trailing_backslash_is_not_treated_as_root(_sandbox):
    candidate = Path(f"{_sandbox}" + chr(92))
    assert ops._is_within(_sandbox, _sandbox) is True
    assert ops._is_within(candidate, _sandbox) is False


def test_redact_consumes_complete_quoted_multiline_safe_value():
    value = 'password: "correct horse battery staple"\nordinary: visible'
    redacted, count = ops.redact(value)

    assert count == 1
    assert 'correct horse battery staple' not in redacted
    assert 'password: "[REDACTED]"' in redacted
    assert 'ordinary: visible' in redacted


def test_redact_does_not_consume_following_line_when_value_is_unquoted():
    value = "password: first-line-secret\nordinary: visible"
    redacted, count = ops.redact(value)

    assert count == 1
    assert "first-line-secret" not in redacted
    assert "ordinary: visible" in redacted


# --------------------------------------------------------------------------- #
# Security review regressions: follow-up hardening
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("quote", ["‘", "’", "‚", "‛", "“", "”", "„", "‟", "＂", "＇"])
def test_powershell_rejects_unicode_quote_delimiters(_fake_powershell, quote):
    with pytest.raises(ValueError, match="quot"):
        ops.compile_command(
            "powershell_readonly",
            "Get-ChildItem",
            ["-Filter", f"safe{quote} -Recurse"],
        )


def test_credential_redaction_is_bounded_for_repeated_secret_prefixes():
    import time

    payload = "SECRET" * 200
    started = time.monotonic()

    sanitized, _ = ops.redact(payload)

    assert sanitized == payload
    assert time.monotonic() - started < 1.0


def test_compile_rejection_for_missing_cwd_is_audited(_sandbox):
    missing = _sandbox / "does-not-exist"

    result = ops.run_host_command("git", "status", [], cwd=str(missing))

    assert result["success"] is False
    assert result["status"] == "command_rejected"
    assert result["audit_logged"] is True
    record = json.loads(_sandbox_audit().read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "rejected"
    assert record["reason"] == "validation_error"


def test_git_commit_probe_timeout_is_audited_rejection(_sandbox, monkeypatch):
    monkeypatch.setattr(ops, "_repository_root", lambda: _sandbox)
    monkeypatch.setattr(ops, "allowed_roots", lambda: (_sandbox,))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))

    monkeypatch.setattr(ops.subprocess, "run", timeout)

    result = ops.run_host_command(
        "git", "show", ["--stat", "HEAD"], cwd=str(_sandbox)
    )

    assert result["success"] is False
    assert result["status"] == "command_rejected"
    assert result["audit_logged"] is True
    record = json.loads(_sandbox_audit().read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "rejected"


@pytest.mark.skipif(os.name != "nt", reason="NTFS path aliases are Windows-specific")
@pytest.mark.parametrize(
    "suffix",
    [
        "file:stream",
        "file.",
        "file ",
        "CON",
        "NUL.txt",
        "COM1.log",
        "LPT9",
        "COM\u00b9",
        "COM\u00b2.txt",
        "LPT\u00b9",
        "LPT\u00b3.log",
    ],
)
def test_resolve_path_rejects_ntfs_aliases(_sandbox, suffix):
    with pytest.raises(ops.PathNotAllowed):
        ops.resolve_path(str(_sandbox / suffix))


def test_spawn_caps_child_output_and_discards_partial_secret_line(_sandbox):
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('safe\nPASSWORD=' + chr(34) + 'x' * 1000000); sys.stderr.write('y' * 1000000)",
    ]

    completed = ops._spawn(command, _sandbox, ops._sanitized_environment(), 10)

    assert completed.stdout.replace("\r\n", "\n") == "safe\n"
    assert "PASSWORD=" not in completed.stdout
    assert len(completed.stdout.encode("utf-8")) <= ops.MAX_STDOUT_CHARS * 4
    assert len(completed.stderr.encode("utf-8")) <= ops.MAX_STDERR_CHARS * 4
    assert completed._jarvis_truncated is True


def test_redact_long_credential_key_names_on_file_and_command_output_paths(_sandbox):
    key = "MY_SUPER_LONG_APPLICATION_CONFIGURATION_ENCRYPTION_PASSWORD"
    secret = "S3cr3t-Pr0d-Passw0rd"
    target = _sandbox / "ordinary-config.yaml"
    target.write_text(f"{key}: {secret}\nmode: safe\n", encoding="utf-8")

    read_result = ops.read_text_file(str(target))
    command_output, _ = ops._bound(f"{key}: {secret}\n", 4_000)

    assert read_result["success"] is True
    assert secret not in read_result["content"]
    assert "[REDACTED]" in read_result["content"]
    assert secret not in command_output
    assert "[REDACTED]" in command_output


def test_redact_incomplete_quoted_credential_value_at_end_of_buffer():
    redacted, count = ops.redact('PASSWORD="unterminated-secret-value')

    assert count == 1
    assert "unterminated-secret-value" not in redacted
    assert "[REDACTED]" in redacted


def test_read_byte_truncation_discards_incomplete_final_line(_sandbox):
    target = _sandbox / "ordinary-config.yaml"
    secret = "long-secret-value-" * 20
    target.write_text(
        "mode: safe\nMY_SUPER_LONG_APPLICATION_CONFIGURATION_ENCRYPTION_PASSWORD: "
        + f'"{secret}"\n',
        encoding="utf-8",
    )

    result = ops.read_text_file(str(target), max_bytes=64)

    assert result["success"] is True
    assert result["truncated"] is True
    assert result["content"] == "mode: safe"
    assert secret not in result["content"]


