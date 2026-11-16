from __future__ import annotations

import os
import stat
import subprocess

import app.adapters.infrastructure.secure_file_permissions as permissions
import pytest
from app.adapters.infrastructure.secure_file_permissions import (
    set_private_directory_permissions,
    set_private_file_permissions,
    verify_private_directory_permissions,
    verify_private_file_permissions,
)


def test_private_directory_and_file_permissions_roundtrip(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir()
    set_private_directory_permissions(directory)

    secret = directory / "profile.json"
    secret.write_text("{}", encoding="utf-8")
    set_private_file_permissions(secret)

    verify_private_directory_permissions(directory)
    verify_private_file_permissions(secret)
    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(secret.stat().st_mode) == 0o600


def test_private_file_verification_rejects_broad_posix_permissions(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX mode-bit assertion does not apply to NTFS ACLs")
    secret = tmp_path / "profile.json"
    secret.write_text("{}", encoding="utf-8")
    secret.chmod(0o644)

    with pytest.raises(PermissionError):
        verify_private_file_permissions(secret)


def test_private_file_verification_rejects_symlinks(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "profile.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(PermissionError):
        verify_private_file_permissions(link)


def test_windows_directory_acl_is_explicitly_restricted_to_user_and_system(
    tmp_path, monkeypatch
):
    directory = tmp_path / "private"
    directory.mkdir()
    calls = []
    user_sid = "S-1-5-21-111-222-333-1001"
    user_name = "TESTHOST\\tester"

    def which(name):
        return name

    def run(command, **_kwargs):
        calls.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(
                command, 0, stdout=f'"{user_name}","{user_sid}"\n', stderr=""
            )
        if "/grant:r" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                f"{directory} {user_name}:(OI)(CI)(F)\n"
                "                  NT AUTHORITY\\SYSTEM:(OI)(CI)(F)\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(permissions.shutil, "which", which)
    monkeypatch.setattr(permissions.subprocess, "run", run)

    permissions._set_windows_acl(directory, directory=True)

    apply_call = next(call for call in calls if "/grant:r" in call)
    assert "/reset" in apply_call
    assert "/inheritance:r" in apply_call
    assert f"*{user_sid}:(OI)(CI)(F)" in apply_call
    assert "*S-1-5-18:(OI)(CI)(F)" in apply_call


def test_windows_acl_verification_rejects_extra_group_access(tmp_path, monkeypatch):
    directory = tmp_path / "private"
    directory.mkdir()
    user_name = "TESTHOST\\tester"
    user_sid = "S-1-5-21-111-222-333-1001"

    def which(name):
        return f"{name}.exe"

    def run(command, **_kwargs):
        if command[0] == "icacls.exe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    f"{directory} {user_name}:(F)\n"
                    "                  NT AUTHORITY\\SYSTEM:(F)\n"
                    "                  BUILTIN\\Users:(RX)\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            command, 0, stdout=f'"{user_name}","{user_sid}"\n', stderr=""
        )

    monkeypatch.setattr(permissions.shutil, "which", which)
    monkeypatch.setattr(permissions.subprocess, "run", run)

    with pytest.raises(PermissionError, match="only to the current user and SYSTEM"):
        permissions._verify_windows_acl(directory)
