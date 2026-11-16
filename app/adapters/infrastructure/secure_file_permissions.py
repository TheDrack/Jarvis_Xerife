"""Cross-platform owner-only permissions for local secret material."""

from __future__ import annotations

import csv
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


def set_private_directory_permissions(path: str | Path) -> None:
    """Restrict a directory to its owner and SYSTEM on Windows."""
    target = Path(path)
    _validate_target(target, directory=True)
    if os.name == "nt":
        _set_windows_acl(target, directory=True)
    else:
        os.chmod(target, 0o700)
        verify_private_directory_permissions(target)


def set_private_file_permissions(path: str | Path) -> None:
    """Restrict a file to its owner and SYSTEM on Windows."""
    target = Path(path)
    _validate_target(target, directory=False)
    if os.name == "nt":
        _set_windows_acl(target, directory=False)
    else:
        os.chmod(target, 0o600)
        verify_private_file_permissions(target)


def verify_private_directory_permissions(path: str | Path) -> None:
    target = Path(path)
    _validate_target(target, directory=True)
    _verify_permissions(target, directory=True)


def verify_private_file_permissions(path: str | Path) -> None:
    target = Path(path)
    _validate_target(target, directory=False)
    _verify_permissions(target, directory=False)


def _validate_target(path: Path, *, directory: bool) -> None:
    if path.is_symlink():
        raise PermissionError("Private storage must not be a symbolic link")
    if not path.exists():
        raise FileNotFoundError(path)
    if directory and not path.is_dir():
        raise PermissionError("Private storage path is not a directory")
    if not directory and not path.is_file():
        raise PermissionError("Private storage path is not a regular file")


def _verify_permissions(path: Path, *, directory: bool) -> None:
    if os.name == "nt":
        _verify_windows_acl(path)
        return
    expected = 0o700 if directory else 0o600
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        kind = "directory" if directory else "file"
        raise PermissionError(
            f"Private storage {kind} permissions must be {expected:04o}"
        )


def _windows_identity() -> tuple[str, str]:
    executable = shutil.which("whoami")
    if not executable:
        raise PermissionError("Windows identity utility is unavailable")
    try:
        result = subprocess.run(
            [executable, "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("Unable to resolve the Windows user SID") from exc
    if result.returncode != 0:
        raise PermissionError("Unable to resolve the Windows user SID")
    for row in csv.reader(line for line in result.stdout.splitlines() if line.strip()):
        if len(row) >= 2 and re.fullmatch(r"S-\d+(?:-\d+)+", row[1].strip()):
            return row[0].strip(), row[1].strip()
    raise PermissionError("Windows identity utility returned an invalid SID")


def _set_windows_acl(path: Path, *, directory: bool) -> None:
    executable = shutil.which("icacls")
    if not executable:
        raise PermissionError("Windows ACL utility is unavailable")
    _user_name, user_sid = _windows_identity()
    inheritance = "(OI)(CI)" if directory else ""
    user_ace = f"*{user_sid}:{inheritance}(F)"
    system_ace = f"*S-1-5-18:{inheritance}(F)"
    try:
        reset = subprocess.run(
            [executable, str(path), "/reset"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if reset.returncode != 0:
            detail = (reset.stderr or reset.stdout).strip().replace("\n", " ")[:240]
            raise PermissionError(
                f"Unable to reset Windows ACL (exit {reset.returncode}): {detail}"
            )
        result = subprocess.run(
            [
                executable,
                str(path),
                "/inheritance:r",
                "/grant:r",
                user_ace,
                system_ace,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("Unable to set private Windows ACL") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:240]
        raise PermissionError(
            f"Unable to set private Windows ACL (exit {result.returncode}): {detail}"
        )
    _verify_windows_acl(path)


def _verify_windows_acl(path: Path) -> None:
    executable = shutil.which("icacls")
    if not executable:
        raise PermissionError("Windows ACL utility is unavailable")
    user_name, _user_sid = _windows_identity()
    try:
        result = subprocess.run(
            [executable, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("Unable to verify private Windows ACL") from exc
    if result.returncode != 0:
        raise PermissionError("Unable to verify private Windows ACL")

    path_text = str(path)
    aces: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if ":(" not in line:
            continue
        if line[: len(path_text)].casefold() == path_text.casefold():
            line = line[len(path_text) :].strip()
        if line and "mandatory label" not in line.casefold():
            aces.append(line)

    user_aliases = {user_name.casefold(), user_name.rsplit("\\", 1)[-1].casefold()}
    has_user = any(
        any(alias and alias in ace.casefold() for alias in user_aliases) for ace in aces
    )
    has_system = any("system" in ace.casefold() for ace in aces)
    has_full_control = all("(F)" in ace for ace in aces)
    if len(aces) != 2 or not has_user or not has_system or not has_full_control:
        raise PermissionError(
            "Private Windows ACL must grant full control only to the current user and SYSTEM"
        )
