"""Read-only host operations exposed through the authenticated Jarvis MCP tunnel.

This module complements :mod:`app.adapters.infrastructure.secure_shell_executor`.
The existing executor validates one PowerShell *string* against an AST allowlist;
this module never builds a shell string from caller input. It accepts a profile
name, a verb and a structured argv, validates every token against a per-verb
policy, and launches the process with ``shell=False``.

Boundaries enforced here:

* every filesystem path must resolve inside an explicit allowed root (repository
  root plus ``D:\\`` on Windows, or ``JARVIS_HOST_OPS_ROOTS``); UNC/device paths,
  mapped drives, ``..`` segments, symlinks and NTFS reparse points are rejected
  before resolution, so caller-controlled links are never followed;
* directories can only be listed (bounded depth/entries) and regular text files
  read (bounded bytes/lines) — credentials by name, private-key blocks and
  API-token shapes are refused/redacted;
* commands run non-elevated, with a minimal environment, a bounded timeout and
  truncated output; destructive, installation, boot, ACL, credential and
  privilege-changing verbs are rejected by pattern even if a confirmation token
  is supplied;
* every execution attempt (accepted or rejected) is logged with an audit id and
  a request digest, never with output content.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from itertools import islice
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)

MAX_PATH_CHARS = 4096
MAX_LIST_DEPTH = 4
MAX_LIST_ENTRIES = 500
MAX_READ_BYTES = 256 * 1024
MAX_READ_LINES = 4_000
MAX_ARGUMENTS = 24
MAX_ARGUMENT_CHARS = 512
MAX_STDOUT_CHARS = 16_000
MAX_STDERR_CHARS = 4_000
MAX_CAPTURE_STDOUT_BYTES = MAX_STDOUT_CHARS * 4
MAX_CAPTURE_STDERR_BYTES = MAX_STDERR_CHARS * 4
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
_AUDIT_SECRET = secrets.token_bytes(32)

PROFILES = ("powershell_readonly", "git", "inspect_d")


class PathNotAllowed(ValueError):
    """Raised when a path is outside the allowed roots or looks like a secret."""


# --------------------------------------------------------------------------- #
# Roots and path resolution
# --------------------------------------------------------------------------- #
def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _reject_network_path(raw: str | Path) -> None:
    """Reject UNC/device paths and mapped network drives before Path.resolve can contact them."""
    text = os.fspath(raw)
    normalized = text.replace("/", "\\")
    if text.startswith(("\\\\", "//")) or normalized.startswith("\\\\"):
        raise PathNotAllowed("UNC and device paths are not permitted")
    if os.name == "nt":
        drive, _tail = os.path.splitdrive(text)
        if drive and len(drive) == 2 and drive[1] == ":":
            try:
                import ctypes

                drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
            except (AttributeError, OSError):
                drive_type = 0
            if drive_type in {0, 1, 4}:
                raise PathNotAllowed("unknown, unavailable or mapped network drives are not permitted")


def _reject_windows_path_aliases(raw: str | Path) -> None:
    """Reject Windows filesystem aliases that can address objects outside a lexical path."""
    if os.name != "nt":
        return
    text = os.fspath(raw).replace("/", "\\")
    _drive, tail = os.path.splitdrive(text)
    for component in tail.split("\\"):
        if not component or component in {".", ".."}:
            continue
        if component.endswith((".", " ")):
            raise PathNotAllowed("trailing dots and spaces are not permitted in Windows paths")
        if ":" in component:
            raise PathNotAllowed("NTFS alternate data streams are not permitted")
        device_name = component.split(".", 1)[0].casefold()
        if device_name in {"con", "prn", "aux", "nul"} or re.fullmatch(
            r"(?:com|lpt)[1-9]", device_name
        ):
            raise PathNotAllowed("reserved Windows device names are not permitted")


def _reject_link_components(candidate: Path) -> None:
    """Reject symlinks and NTFS reparse points before resolving their targets."""
    absolute = candidate if candidate.is_absolute() else candidate.absolute()
    current = Path(absolute.anchor)
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PathNotAllowed("path component could not be inspected safely") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise PathNotAllowed("symlink path components are not permitted")
        if getattr(metadata, "st_file_attributes", 0) & reparse_point:
            raise PathNotAllowed("NTFS reparse-point path components are not permitted")


def allowed_roots() -> tuple[Path, ...]:
    """Return the effective allowlist of filesystem roots.

    ``JARVIS_HOST_OPS_ROOTS`` (os.pathsep-separated) replaces the default. The
    repository root is always appended so relative tool paths keep working.
    """
    configured = os.environ.get("JARVIS_HOST_OPS_ROOTS", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.extend(
            Path(part).expanduser() for part in configured.split(os.pathsep) if part.strip()
        )
    else:
        if os.name == "nt":
            candidates.append(Path("D:/"))
    candidates.append(_repository_root())

    roots: list[Path] = []
    for candidate in candidates:
        try:
            if not candidate.is_absolute():
                raise PathNotAllowed("allowed roots must be absolute local paths")
            _reject_network_path(candidate)
            _reject_link_components(candidate)
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _norm(value: Path | str) -> str:
    # Preserve trailing separators: on POSIX a backslash is a valid filename character.
    return os.path.normcase(str(value))


def _is_within(path: Path, root: Path) -> bool:
    normalized_path = _norm(path)
    normalized_root = _norm(root)
    if normalized_path == normalized_root:
        return True
    prefix = normalized_root if normalized_root.endswith(os.sep) else normalized_root + os.sep
    return normalized_path.startswith(prefix)


def _is_secret_path(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    if any(part in _SECRET_DIRECTORIES for part in parts):
        return True
    if _SECRET_FILE_NAME.match(path.name):
        return True
    for prefix in _SECRET_PATH_PREFIXES:
        width = len(prefix)
        if any(parts[index:index + width] == prefix for index in range(len(parts) - width + 1)):
            return True
    return False


def _reject_secret_name(path: Path) -> None:
    if _is_secret_path(path):
        raise PathNotAllowed("path looks like a credential store")


def resolve_path(raw: str, *, must_exist: bool = False) -> Path:
    """Resolve one caller-supplied path inside an allowed root.

    Rejects traversal before resolution, then resolves symlinks/junctions and
    checks containment again so a link cannot point outside the allowlist.
    """
    if not isinstance(raw, str):
        raise PathNotAllowed("path must be a string")
    text = raw.strip()
    if not text or len(text) > MAX_PATH_CHARS:
        raise PathNotAllowed(f"path must contain 1 to {MAX_PATH_CHARS} characters")
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise PathNotAllowed("path contains control characters")
    if text.startswith("~"):
        raise PathNotAllowed("home-relative paths are not accepted; use an absolute allowed root")
    _reject_network_path(text)
    _reject_windows_path_aliases(text)
    # A Windows drive-absolute path must never be reinterpreted as a relative
    # POSIX path (for example, C:/Windows under the repository root).
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", text):
        raise PathNotAllowed("Windows drive paths are not valid on this host")
    if ":" in text and not re.match(r"^[A-Za-z]:[\\/]", text):
        raise PathNotAllowed("provider-qualified and drive-relative paths are not accepted")
    if re.split(r"[\\/]+", text).count("..") or ".." in re.split(r"[\\/]+", text):
        raise PathNotAllowed("parent traversal is not permitted")

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = _repository_root() / candidate
    _reject_link_components(candidate)
    try:
        resolved = candidate.resolve()
    except OSError as exc:  # pragma: no cover - platform specific failures
        raise PathNotAllowed(f"path could not be resolved: {type(exc).__name__}") from exc

    roots = allowed_roots()
    if not any(_is_within(resolved, root) for root in roots):
        raise PathNotAllowed("path is outside the allowed roots")
    if must_exist and not resolved.exists():
        raise FileNotFoundError("path does not exist")
    return resolved


_SECRET_DIRECTORIES = frozenset(
    {".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".password-store", ".git", ".terraform", ".vault", "credentials", "secrets", "tokens", "passwords", "gcloud", "gh", "containers", "keyrings", "globalstorage", "github cli"}
)
_SECRET_FILE_NAME = re.compile(
    r"""(?ix)^(
        .*\.env(\..*)?
        |\.npmrc|\.pypirc|\.netrc|_netrc|\.envrc|\.git-credentials|credential([._-].*)?
        |id_(rsa|dsa|ecdsa|ed25519)(\..*)?
        |kubeconfig([._-].*)?|admin\.conf
        |credentials?([._-].*)?
        |(.*[._-])?secrets?([._-].*)?
        |tokens?(\..*)?
        |\.pgpass(\..*)?|pgpass\.conf(\..*)?|\.htpasswd|\.boto|\.s3cfg|\.my\.cnf
        |client[_-]?secret.*\.json(\..*)?|application_default_credentials.*\.json(\..*)?
        |.*\.(pem|key|pfx|p12|jks|keystore|kdbx|asc|ppk|p8|ovpn|gpg|pgp)(\..*)?
        |.*\.(tfvars|tfstate)(\..*)?
        |.*\.(sqlite|sqlite3|db)(\..*)?
        |\.yarnrc\.yml
    )$"""
)
_SECRET_PATH_PREFIXES = (
    (".config", "gh"),
    (".config", "glab-cli"),
    (".config", "github-copilot"),
    (".config", "composer"),
    (".config", "containers"),
    (".config", "age"),
    (".config", "ngrok"),
    (".config", "op"),
    (".config", "sops"),
    (".config", "gcloud"),
    (".config", "rclone"),
    (".config", "hub"),
    (".config", "podman"),
    (".config", "keyring"),
    (".m2",),
    (".gem", "credentials"),
)

_SENSITIVE_OUTPUT_NAME = re.compile(
    r"(?i)(?<![A-Z0-9_.-])(?:"
    r"\.env(?:\.[A-Z0-9_-]+)?|\.envrc|\.aws|\.azure|\.ssh|\.gnupg|\.kube|\.docker|"
    r"\.password-store|\.terraform|\.vault|\.git-credentials|\.npmrc|\.pypirc|\.netrc|_netrc|"
    r"\.pgpass(?:\.[A-Z0-9_-]+)?|\.htpasswd|\.boto|\.s3cfg|\.my\.cnf|\.m2|"
    r"gh|glab-cli|github-copilot|composer|age|ngrok|gcloud|rclone|hub|podman|"
    r"containers|keyrings|globalstorage|github cli|"
    r"kubeconfig(?:[._-][A-Z0-9_-]+)*|credentials?(?:[._-][A-Z0-9_-]+)*|"
    r"secrets?(?:[._-][A-Z0-9_-]+)*|tokens?(?:[._-][A-Z0-9_-]+)*|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\.[A-Z0-9_-]+)?|"
    r"client_secret(?:\.[A-Z0-9_-]+)*|application_default_credentials(?:\.[A-Z0-9_-]+)*"
    r")(?![A-Z0-9_.-])"
)

_SECRET_CONTENT = re.compile(
    rb"(?i)(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|\"auths\"\s*:|_authToken|npmAuthToken|oauth_token|AGE-SECRET-KEY-|"
    rb"gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{16,}|"
    rb"xox[abposr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|"
    rb"<\s*(?:password|token|secret|api[_-]?key)\b[^>]*>\s*[^<]{4,}</\s*(?:password|token|secret|api[_-]?key)\s*>)"
)

_PRIVATE_KEY_BLOCK = re.compile(
    r"(?:-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
    r"|-----BEGIN PGP PRIVATE KEY BLOCK-----"
    r"|---- BEGIN SSH2 ENCRYPTED PRIVATE KEY ----"
    r"|-----BEGIN OpenVPN Static key V1-----"
    r"|PuTTY-User-Key-File-\d+:"
    r"|AGE-SECRET-KEY-1[A-Z0-9]+)",
    re.IGNORECASE,
)
_BINARY_PROBE = 8192


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
def _redact_credential_value(match: re.Match[str]) -> str:
    """Replace the complete credential value, preserving its quote style."""
    value = match.group(2)
    quote = value[0] if value[:1] in {'"', "'"} else ""
    return f"{match.group(1)}{quote}[REDACTED]{quote}"


_REDACTION_RULES: tuple[tuple[re.Pattern[str], Any], ...] = (
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{8,}=*"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}|\bnpm_[A-Za-z0-9]{16,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|APKA|AROA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    (
        re.compile(
            r"""(?i)((?:client[_-]?key[_-]?data|certificate[_-]?authority[_-]?data|account[_-]?key)["']?\s*[:=]\s*["']?)([^"'\s,;}]{8,})"""
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"""([a-z][a-z0-9+.-]*://[^/\s:@"']*:)([^@\s/"']+)@"""),
        r"\1[REDACTED]@",
    ),
    (
        re.compile(
            r"""(?i)(["']?\b[A-Z0-9_]{0,40}(?:API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|SIGNING[_-]?KEY|AUTH[_-]?TOKEN|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|CLIENT[_-]?SECRET|SERVICE[_-]?ROLE[_-]?KEY|SECRET[A-Z0-9_-]{0,40}|TOKEN|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL)[A-Z0-9_]{0,40}["']?[ \t]*[:=][ \t]*)((?:"[^"\n]*"|'[^'\n]*'|[^"'\s,;}]+))"""
        ),
        _redact_credential_value,
    ),
)


def redact(value: str) -> tuple[str, int]:
    """Return ``(redacted_text, replacements)`` for credential-shaped content."""
    text = value or ""
    total = 0
    for pattern, replacement in _REDACTION_RULES:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


# --------------------------------------------------------------------------- #
# Filesystem listing
# --------------------------------------------------------------------------- #
def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _is_junction(entry: os.DirEntry[str]) -> bool:
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    try:
        import ctypes

        kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
        if kernel32 is not None:
            attributes = kernel32.GetFileAttributesW(ctypes.c_wchar_p(entry.path))
            if attributes != 0xFFFFFFFF and attributes & reparse_point:
                return not entry.is_symlink()
    except (AttributeError, OSError):
        pass
    checker = getattr(os.path, "isjunction", None)
    if checker is not None:
        try:
            if checker(entry.path):
                return True
        except OSError:
            return False
    try:
        attributes = entry.stat(follow_symlinks=False).st_file_attributes
        return bool(attributes & reparse_point) and not entry.is_symlink()
    except (AttributeError, OSError):
        return False


def _entry_kind(entry: os.DirEntry[str]) -> str:
    if entry.is_symlink():
        return "symlink"
    if _is_junction(entry):
        return "junction"
    if entry.is_dir(follow_symlinks=False):
        return "directory"
    if entry.is_file(follow_symlinks=False):
        return "file"
    return "other"


def list_directory(
    path: str = ".", depth: int = 1, max_entries: int = 200
) -> dict[str, Any]:
    """List directory metadata under an allowed root without reading content."""
    depth = _bounded_int(depth, name="depth", minimum=0, maximum=MAX_LIST_DEPTH)
    max_entries = _bounded_int(
        max_entries, name="max_entries", minimum=1, maximum=MAX_LIST_ENTRIES
    )
    root = resolve_path(path, must_exist=True)
    _reject_secret_name(root)
    if not root.is_dir():
        raise ValueError("path is not a directory")

    entries: list[dict[str, Any]] = []
    filtered = 0
    truncated = False

    def walk(current: Path, level: int) -> None:
        nonlocal filtered, truncated
        if truncated:
            return
        try:
            scanner = os.scandir(current)
            try:
                children = list(islice(scanner, max_entries + 1))
            finally:
                close = getattr(scanner, "close", None)
                if close is not None:
                    close()
            scan_truncated = len(children) > max_entries
            children = sorted(
                children[:max_entries],
                key=lambda item: (
                    not item.is_dir(follow_symlinks=False),
                    item.name.casefold(),
                ),
            )
        except PermissionError:
            entries.append(
                {
                    "name": current.name,
                    "path": _relative(current, root),
                    "kind": "directory",
                    "depth": level,
                    "error": "permission_denied",
                }
            )
            return
        for entry in children:
            if len(entries) >= max_entries:
                truncated = True
                return
            if _is_secret_path(Path(entry.path)):
                filtered += 1
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                stat = None
            kind = _entry_kind(entry)
            entries.append(
                {
                    "name": entry.name,
                    "path": _relative(Path(entry.path), root),
                    "kind": kind,
                    "depth": level,
                    "size": None if kind == "directory" else (stat.st_size if stat else None),
                    "modified": _iso(stat.st_mtime) if stat else None,
                    "hidden": entry.name.startswith("."),
                }
            )
            if kind == "directory" and level < depth:
                walk(Path(entry.path), level + 1)
        if scan_truncated:
            truncated = True

    walk(root, 0)
    return {
        "success": True,
        "status": "listed",
        "root": str(root),
        "depth": depth,
        "entries": entries,
        "entry_count": len(entries),
        "filtered_secret_entries": filtered,
        "truncated": truncated,
        "max_entries": max_entries,
        "followed_symlinks": False,
    }


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)) or "."
    except ValueError:  # pragma: no cover - defensive
        return path.name


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Text reading
# --------------------------------------------------------------------------- #
def read_text_file(
    path: str, max_bytes: int = 65_536, max_lines: int = 2_000
) -> dict[str, Any]:
    """Read one bounded text file, refusing credentials and private keys."""
    max_bytes = _bounded_int(max_bytes, name="max_bytes", minimum=1, maximum=MAX_READ_BYTES)
    max_lines = _bounded_int(max_lines, name="max_lines", minimum=1, maximum=MAX_READ_LINES)
    resolved = resolve_path(path, must_exist=True)
    _reject_secret_name(resolved)
    if not resolved.is_file():
        raise ValueError("path is not a regular file")

    total_bytes = resolved.stat().st_size
    with resolved.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if b"\x00" in data[:_BINARY_PROBE]:
        return {
            "success": False,
            "status": "binary_file",
            "path": str(resolved),
            "total_bytes": total_bytes,
            "message": "binary content is not returned by this tool",
        }
    if _SECRET_CONTENT.search(data):
        return {
            "success": False,
            "status": "secret_content_blocked",
            "path": str(resolved),
            "total_bytes": total_bytes,
            "message": "file contains stored credential material",
        }
    text = data.decode("utf-8", errors="replace")
    if _PRIVATE_KEY_BLOCK.search(text):
        return {
            "success": False,
            "status": "secret_content_blocked",
            "path": str(resolved),
            "total_bytes": total_bytes,
            "message": "file contains a private key block",
        }

    truncated_by_bytes = len(data) > max_bytes
    if truncated_by_bytes:
        text = data[:max_bytes].decode("utf-8", errors="replace")
    redacted, redactions = redact(text)
    lines = redacted.splitlines()
    truncated_by_lines = len(lines) > max_lines
    lines = lines[:max_lines]
    return {
        "success": True,
        "status": "read",
        "path": str(resolved),
        "content": "\n".join(lines),
        "lines_returned": len(lines),
        "max_lines": max_lines,
        "bytes_returned": len(redacted.encode("utf-8")),
        "total_bytes": total_bytes,
        "max_bytes": max_bytes,
        "truncated": truncated_by_bytes or truncated_by_lines,
        "redactions": redactions,
        "encoding": "utf-8",
        "lossy_decode": "\ufffd" in redacted,
    }


# --------------------------------------------------------------------------- #
# Command profiles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ArgumentPolicy:
    """Per-verb parameter policy for a structured command."""

    values: Mapping[str, str]  # parameter -> validator name
    flags: frozenset[str]
    positional: str | None = None  # validator name for positional tokens


_SHELL_METACHARACTERS = re.compile(r"[;&|`$<>(){}\[\]\r\n\x00]")
_PATH_VALIDATOR = re.compile(r"^[\w .:\\/~()\-]{1,260}$")
_REF_VALIDATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/~^@{}-]{0,127}$")
_EXPRESSION_VALIDATOR = re.compile(r"^[A-Za-z0-9_\-\[\]: .]{1,120}$")
_INTEGER_VALIDATOR = re.compile(r"^\d{1,4}$")
_ALGORITHM_VALIDATOR = re.compile(r"^(SHA256|SHA384|SHA512)$")

_POWERSHELL_POLICIES: dict[str, ArgumentPolicy] = {
    "Get-ChildItem": ArgumentPolicy(
        values={"Path": "path", "Name": "path", "Depth": "integer", "Filter": "text"},
        flags=frozenset({"-File", "-Directory"}),
        positional="path",
    ),
    "Get-Item": ArgumentPolicy(values={"Path": "path"}, flags=frozenset(), positional="path"),
    "Test-Path": ArgumentPolicy(
        values={"Path": "path", "PathType": "text"}, flags=frozenset(), positional="path"
    ),
    "Resolve-Path": ArgumentPolicy(
        values={"Path": "path"}, flags=frozenset(), positional="path"
    ),
    "Get-FileHash": ArgumentPolicy(
        values={"Path": "path", "Algorithm": "algorithm"}, flags=frozenset(), positional="path"
    ),
    "Get-Process": ArgumentPolicy(
        values={"Name": "text", "Id": "integer"}, flags=frozenset()
    ),
    "Get-Service": ArgumentPolicy(
        values={"Name": "text", "DisplayName": "text"}, flags=frozenset()
    ),
    "Get-NetTCPConnection": ArgumentPolicy(
        values={
            "State": "text",
            "LocalPort": "integer",
            "RemotePort": "integer",
            "OwningProcess": "integer",
        },
        flags=frozenset(),
    ),
    "Get-NetAdapter": ArgumentPolicy(
        values={"Name": "text", "InterfaceDescription": "text"}, flags=frozenset()
    ),
    "Get-PSDrive": ArgumentPolicy(
        values={"Name": "text", "PSProvider": "text"}, flags=frozenset()
    ),
    "Get-ComputerInfo": ArgumentPolicy(values={"Property": "text"}, flags=frozenset()),
    "Get-Date": ArgumentPolicy(values={}, flags=frozenset()),
}

_GIT_POLICIES: dict[str, ArgumentPolicy] = {
    "status": ArgumentPolicy(
        values={},
        flags=frozenset(
            {"--short", "-s", "--porcelain", "--branch", "--ignore-submodules", "--untracked-files=no"}
        ),
    ),
    "log": ArgumentPolicy(
        values={"-n": "integer", "--max-count": "integer"},
        flags=frozenset(
            {"--oneline", "--stat", "--name-only", "--no-color", "--decorate", "--graph", "--all"}
        ),
        positional="ref",
    ),
    "diff": ArgumentPolicy(
        values={},
        flags=frozenset({"--stat", "--name-only", "--no-color", "--cached", "--staged"}),
        positional="ref",
    ),
    "show": ArgumentPolicy(
        values={},
        flags=frozenset({"--stat", "--name-only", "--no-color"}),
        positional="ref",
    ),
    "rev-parse": ArgumentPolicy(
        values={},
        flags=frozenset({"--short", "--abbrev-ref", "--show-toplevel", "--verify"}),
        positional="ref",
    ),
    "ls-files": ArgumentPolicy(
        values={},
        flags=frozenset({"--cached", "--modified", "--others", "--exclude-standard", "--deleted"}),
    ),
    "branch": ArgumentPolicy(
        values={}, flags=frozenset({"--list", "-a", "-r", "-v", "--verbose"})
    ),
    "describe": ArgumentPolicy(
        values={}, flags=frozenset({"--tags", "--always", "--dirty", "--long"})
    ),
}

_INSPECT_D_POLICIES: dict[str, ArgumentPolicy] = {
    "Get-ChildItem": ArgumentPolicy(
        values={"Path": "d_path", "Name": "d_path", "Depth": "integer", "Filter": "text"},
        flags=frozenset({"-File", "-Directory"}),
        positional="d_path",
    ),
    "Get-Item": ArgumentPolicy(values={"Path": "d_path"}, flags=frozenset(), positional="d_path"),
}

_HARD_BLOCK_PATTERNS = re.compile(
    r"""(?ix)\b(
        remove-item|del|erase|rmdir|rd|format|format-volume|clear-disk|initialize-disk|
        diskpart|mkfs|mke2fs|fdisk|parted|sgdisk|dd|
        bcdedit|bootrec|efibootmgr|grub-install|update-grub|
        reg(\s+(add|delete|import|load|restore))?|
        icacls|takeown|cacls|set-acl|get-acl\s+.*\s*\|\s*set-acl|
        schtasks|set-executionpolicy|new-item|set-item|set-itemproperty|
        add-content|set-content|out-file|rename-item|move-item|copy-item|
        stop-process|start-process|stop-service|start-service|restart-service|
        invoke-expression|invoke-command|invoke-webrequest|invoke-restmethod|iex|
        new-localuser|net\s+user|net\s+localgroup|add-localgroupmember|
        sudo|runas|start-job|register-scheduledtask|unregister-scheduledtask|
        install-package|apt(-get)?\s+install|pip\s+install|npm\s+install|winget|choco
    )\b"""
)

_GIT_FORBIDDEN = re.compile(
    r"(?i)(^|\s)(-c\b|-C\b|--exec-path|--upload-pack|--receive-pack|--git-dir|--work-tree|--config-env)"
)


@dataclass(frozen=True)
class CompiledCommand:
    profile: str
    verb: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    display: str


def _validate_argument_value(validator: str, value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("argument values must be strings")
    if not value or len(value) > MAX_ARGUMENT_CHARS:
        raise ValueError(f"argument values must contain 1 to {MAX_ARGUMENT_CHARS} characters")
    if _SHELL_METACHARACTERS.search(value):
        raise ValueError("argument contains shell metacharacters")
    if validator == "integer":
        if not _INTEGER_VALIDATOR.match(value):
            raise ValueError("expected an integer argument")
        return
    if validator == "algorithm":
        if not _ALGORITHM_VALIDATOR.match(value):
            raise ValueError("algorithm must be SHA256, SHA384 or SHA512")
        return
    if validator == "ref":
        if not _REF_VALIDATOR.match(value):
            raise ValueError("invalid ref or path argument")
        return
    if validator in {"path", "d_path"}:
        if not _PATH_VALIDATOR.match(value):
            raise ValueError("invalid path argument")
        # PowerShell provider paths are not filesystem paths. Reject namespace
        # separators and every colon except an absolute Windows drive prefix.
        if "::" in value or (
            ":" in value and not re.match(r"^[A-Za-z]:[\\/]", value)
        ):
            raise PathNotAllowed("only filesystem paths are permitted")
        resolved = resolve_path(value)
        _reject_secret_name(resolved)
        if validator == "d_path" and not _norm(resolved).startswith(_norm(Path("D:/"))):
            raise PathNotAllowed("this profile can only inspect D:\\")
        return
    if not value.strip():  # pragma: no cover - covered by the empty check
        raise ValueError("argument values must not be blank")


def _parse_arguments(
    verb: str, arguments: Sequence[str], policy: ArgumentPolicy
) -> list[tuple[str, str | None]]:
    if isinstance(arguments, (str, bytes)) or not isinstance(arguments, Sequence):
        raise ValueError("arguments must be a list of strings")
    if len(arguments) > MAX_ARGUMENTS:
        raise ValueError(f"at most {MAX_ARGUMENTS} arguments are accepted")
    parsed: list[tuple[str, str | None]] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if not isinstance(token, str) or not token:
            raise ValueError("arguments must be non-empty strings")
        if len(token) > MAX_ARGUMENT_CHARS:
            raise ValueError("argument is too long")
        if _SHELL_METACHARACTERS.search(token):
            raise ValueError("argument contains shell metacharacters")
        if token.startswith("-"):
            # PowerShell and most CLIs treat parameter names case-insensitively.
            flag = next(
                (item for item in policy.flags if item.casefold() == token.casefold()), None
            )
            if flag is not None:
                parsed.append((flag, None))
                index += 1
                continue
            bare = token.lstrip("-").casefold()
            parameter = next(
                (
                    item
                    for item in policy.values
                    if item.casefold() in {bare, token.casefold()}
                ),
                None,
            )
            if parameter is None:
                raise ValueError(f"parameter {token} is not allowlisted for {verb}")
            validator = policy.values[parameter]
            if index + 1 >= len(arguments):
                raise ValueError(f"parameter {token} requires a value")
            value = arguments[index + 1]
            _validate_argument_value(validator, value)
            parsed.append((parameter, value))
            index += 2
            continue
        if policy.positional is None:
            raise ValueError(f"{verb} does not accept positional arguments")
        _validate_argument_value(policy.positional, token)
        parsed.append(("", token))
        index += 1
    return parsed


_UNICODE_QUOTE_CHARS = "‘’‚‛“”„‟＂＇"


def _powershell_quote(value: str) -> str:
    if "'" in value or "`" in value or any(char in value for char in _UNICODE_QUOTE_CHARS):
        raise ValueError("PowerShell argument quoting rejected")
    return f"'{value}'"


def _compile_powershell(
    profile: str, verb: str, parsed: Iterable[tuple[str, str | None]]
) -> str:
    tokens = [verb]
    for parameter, value in parsed:
        if parameter:
            tokens.append(parameter if parameter.startswith("-") else f"-{parameter}")
        if value is not None:
            tokens.append(_powershell_quote(value))
    return " ".join(tokens)


def _sanitized_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    allowed = (
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "ProgramData",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.setdefault("PATH", os.defpath)
    environment["POWERSHELL_TELEMETRY_OPTOUT"] = "1"
    environment["GIT_PAGER"] = "cat"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        environment.update(extra)
    return environment


def _require_commitish(ref: str, workdir: Path) -> None:
    """Reject blob/tree targets that would make git show disclose raw content."""
    environment = _sanitized_environment()
    environment["GIT_CEILING_DIRECTORIES"] = str(_repository_root())
    try:
        probe = subprocess.run(
            [
                "git", "-c", "core.fsmonitor=false",
                "-c", "core.untrackedCache=false",
                "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
            ],
            cwd=str(workdir),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MIN_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("git show commit validation is unavailable") from exc
    if probe.returncode != 0:
        raise ValueError("git show targets must resolve to a commit")


def _powershell_executable() -> str | None:
    for name in ("powershell.exe", "pwsh.exe", "pwsh"):
        found = shutil.which(name)
        if found:
            return found
    return None


def compile_command(
    profile: str,
    verb: str,
    arguments: Sequence[str] | None = None,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 20,
) -> CompiledCommand:
    """Validate a structured command against the profile policy."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
    if not isinstance(verb, str) or not verb.strip():
        raise ValueError("verb is required")
    arguments = list(arguments or [])
    timeout_seconds = _bounded_int(
        timeout_seconds,
        name="timeout_seconds",
        minimum=MIN_TIMEOUT_SECONDS,
        maximum=MAX_TIMEOUT_SECONDS,
    )
    joined = " ".join([verb, *arguments])
    blocked = _HARD_BLOCK_PATTERNS.search(joined)
    if blocked:
        raise PermissionError(f"operation is blocked by policy: {blocked.group(0).strip()}")

    workdir = resolve_path(cwd, must_exist=True) if cwd else _repository_root()
    if not workdir.is_dir():
        raise ValueError("working directory is not a directory")
    if profile == "git" and not _is_within(workdir, _repository_root()):
        raise PathNotAllowed("git must run inside the repository root")
    if profile in {"powershell_readonly", "inspect_d"} and _norm(workdir) != _norm(_repository_root()):
        raise PathNotAllowed("PowerShell profiles use the repository root as cwd; pass absolute paths")

    if profile == "git":
        policy = _GIT_POLICIES.get(verb)
        if policy is None:
            raise ValueError("git subcommand is not allowlisted")
        if any(_GIT_FORBIDDEN.search(argument) for argument in arguments):
            raise ValueError("git options that relocate the repository are not permitted")
        if verb in {"show", "diff"} and not {"--stat", "--name-only"}.intersection(arguments):
            raise ValueError("git show/diff must use metadata-only --stat or --name-only output")
        parsed = _parse_arguments(verb, arguments, policy)
        metadata_flags = {flag for flag, _value in parsed if flag} & {"--stat", "--name-only"}
        if verb in {"show", "diff"} and not metadata_flags:
            raise ValueError("git show/diff must use metadata-only --stat or --name-only output")
        if verb == "show":
            for parameter, value in parsed:
                if parameter == "" and value is not None:
                    _require_commitish(value, workdir)
        argv = (
            "git",
            "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "-c", "log.showSignature=false",
            "--no-pager",
            *(
                (verb, "--no-ext-diff", "--no-textconv")
                if verb in {"show", "diff"}
                else (verb,)
            ),
            *[token for pair in parsed for token in pair if token],
        )
        return CompiledCommand(profile, verb, argv, workdir, timeout_seconds, joined)

    policies = _INSPECT_D_POLICIES if profile == "inspect_d" else _POWERSHELL_POLICIES
    policy = policies.get(verb)
    if policy is None:
        raise ValueError("PowerShell verb is not allowlisted for this profile")
    parsed = _parse_arguments(verb, arguments, policy)
    if profile == "inspect_d" and not any(
        parameter in {"Path", "Name", ""} for parameter, _value in parsed
    ):
        raise ValueError("inspect_d requires an explicit D:\\ path")
    executable = _powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell is not available on this host")
    command_text = _compile_powershell(profile, verb, parsed)
    argv = (
        executable,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        command_text,
    )
    return CompiledCommand(profile, verb, argv, workdir, timeout_seconds, command_text)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def _audit_path() -> Path:
    configured = os.environ.get("JARVIS_HOST_OPS_AUDIT_LOG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "jarvis" / "host_ops_audit.jsonl"


def _audit_argument_digest(arguments: Sequence[Any]) -> str:
    try:
        payload = json.dumps(
            list(arguments),
            sort_keys=True,
            ensure_ascii=False,
            default=lambda value: f"<{type(value).__name__}>",
        )
    except (TypeError, ValueError):
        payload = f"<{type(arguments).__name__}>"
    return hmac.new(_AUDIT_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _request_digest(profile: str, verb: str, arguments: Sequence[str], cwd: Path) -> str:
    payload = json.dumps(
        {"profile": profile, "verb": verb, "arguments": list(arguments), "cwd": str(cwd)},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _audit(record: Mapping[str, Any]) -> tuple[str, bool]:
    audit_id = uuid.uuid4().hex[:12]
    payload = {"ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"), "audit_id": audit_id, **record}
    if "profile" in payload and payload["profile"] not in PROFILES:
        payload["profile"] = "unknown"
    if "verb" in payload:
        allowed_verbs = set(_POWERSHELL_POLICIES) | set(_GIT_POLICIES) | set(_INSPECT_D_POLICIES)
        if payload["verb"] not in allowed_verbs:
            payload["verb"] = "unknown"
    if "reason" in payload:
        payload["reason"] = "validation_error"
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            if os.name != "nt":
                os.chmod(path, 0o600)
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return audit_id, True
    except OSError as exc:  # pragma: no cover - filesystem failure
        logger.warning("Host ops audit write failed: %s", type(exc).__name__)
        return audit_id, False


# --------------------------------------------------------------------------- #
# Confirmation gate
# --------------------------------------------------------------------------- #
_CONFIRM_SECRET = secrets.token_bytes(32)
_CONFIRM_TTL_SECONDS = 120
# No host capability is confirmable today: destructive, installation, boot,
# ACL, credential and privilege operations are hard-blocked above. Capabilities
# may only be added here together with a policy review and regression tests.
_CONFIRMABLE_PROFILES: frozenset[str] = frozenset()
_USED_TOKENS: set[str] = set()


def request_confirmation(
    profile: str, verb: str, arguments: Sequence[str] | None = None, cwd: str | None = None
) -> dict[str, Any]:
    """Issue a single-use confirmation token for a confirmable capability."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
    arguments = list(arguments or [])
    compiled = compile_command(profile, verb, arguments, cwd=cwd)
    if profile not in _CONFIRMABLE_PROFILES:
        return {
            "success": False,
            "status": "confirmation_not_applicable",
            "profile": profile,
            "message": (
                "This capability is read-only and needs no confirmation. Destructive, "
                "installation, boot, ACL, credential and privileged operations are "
                "hard-blocked regardless of confirmation."
            ),
        }
    digest = _request_digest(profile, verb, arguments, compiled.cwd)
    expiry = int(time.time()) + _CONFIRM_TTL_SECONDS
    body = f"{digest}.{expiry}"
    signature = hmac.new(_CONFIRM_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "success": True,
        "status": "confirmation_required",
        "token": f"{body}.{signature}",
        "expires_in_seconds": _CONFIRM_TTL_SECONDS,
        "single_use": True,
        "request_digest": digest[:16],
    }


def _consume_confirmation(token: str, digest: str) -> bool:
    if not isinstance(token, str) or token.count(".") != 2:
        return False
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(_CONFIRM_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    token_digest, raw_expiry = body.split(".", 1)
    if not raw_expiry.isdigit() or int(raw_expiry) < int(time.time()):
        return False
    if not hmac.compare_digest(token_digest, digest):
        return False
    if token in _USED_TOKENS:
        return False
    _USED_TOKENS.add(token)
    return True


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def _spawn(
    argv: Sequence[str], cwd: Path, environment: Mapping[str, str], timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    """Run a child while draining pipes and retaining only bounded output."""
    process = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        bufsize=0,
    )
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    stdout_overflow = [False]
    stderr_overflow = [False]

    def drain(stream: Any, buffer: bytearray, limit: int, overflow: list[bool]) -> None:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            remaining = limit - len(buffer)
            if remaining > 0:
                buffer.extend(chunk[:remaining])
            if len(chunk) > max(remaining, 0):
                overflow[0] = True

    assert process.stdout is not None and process.stderr is not None
    readers = (
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout_buffer, MAX_CAPTURE_STDOUT_BYTES, stdout_overflow),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr_buffer, MAX_CAPTURE_STDERR_BYTES, stderr_overflow),
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()

    def decoded(buffer: bytearray) -> str:
        return bytes(buffer).decode("utf-8", errors="replace")

    try:
        return_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        process.wait()
        for reader in readers:
            reader.join(timeout=2)
        timeout_error = subprocess.TimeoutExpired(
            list(argv),
            timeout_seconds,
            output=decoded(stdout_buffer),
            stderr=decoded(stderr_buffer),
        )
        timeout_error._jarvis_truncated = stdout_overflow[0] or stderr_overflow[0]
        raise timeout_error
    finally:
        for reader in readers:
            reader.join(timeout=2)
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass

    completed = subprocess.CompletedProcess(
        list(argv), return_code, decoded(stdout_buffer), decoded(stderr_buffer)
    )
    completed._jarvis_truncated = stdout_overflow[0] or stderr_overflow[0]
    return completed


def _names_credential_entry(token: str) -> bool:
    """Return True when a command-output token names a credential store."""
    cleaned = token.strip("\"'()[]{}<>,;:")
    if not cleaned:
        return False
    parts = [part for part in re.split(r"[\\/]+", cleaned) if part]
    if any(part.casefold() in _SECRET_DIRECTORIES for part in parts):
        return True
    return bool(parts and _SECRET_FILE_NAME.match(parts[-1]))


def _drop_credential_lines(value: str) -> str:
    """Remove output rows that disclose credential-store names or metadata."""
    kept: list[str] = []
    for line in value.splitlines():
        tokens = line.split()
        if any(_names_credential_entry(token) for token in tokens):
            kept.append("[REDACTED_NAME]")
            continue
        if _SENSITIVE_OUTPUT_NAME.search(line):
            kept.append("[REDACTED_LINE]")
            continue
        kept.append(line)
    return "\n".join(kept)


def _bound(value: str | None, limit: int) -> tuple[str, bool]:
    raw = value or ""
    if _PRIVATE_KEY_BLOCK.search(raw):
        return "[WITHHELD: output contained a private key block]", True
    redacted, _ = redact(raw)
    if _PRIVATE_KEY_BLOCK.search(redacted):
        return "[WITHHELD: output contained a private key block]", True
    filtered = _drop_credential_lines(redacted)
    return filtered[:limit], len(raw) > limit or len(filtered) > limit


def run_host_command(
    profile: str,
    verb: str,
    arguments: Sequence[str] | None = None,
    *,
    cwd: str | None = None,
    timeout_seconds: int = 20,
    confirm_token: str | None = None,
) -> dict[str, Any]:
    """Run one allowlisted read-only command with structured argv (never a shell)."""
    arguments = list(arguments or [])
    try:
        compiled = compile_command(
            profile, verb, arguments, cwd=cwd, timeout_seconds=timeout_seconds
        )
    except PermissionError as exc:
        audit_id, logged = _audit(
            {
                "event": "blocked",
                "profile": profile,
                "verb": verb,
                "argument_count": len(arguments),
                "argument_digest": _audit_argument_digest(arguments),
                "reason": str(exc),
                "elevated": False,
            }
        )
        return {
            "success": False,
            "status": "operation_blocked",
            "profile": profile,
            "error": str(exc),
            "audit_id": audit_id,
            "audit_logged": logged,
            "elevated": False,
        }
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        audit_id, logged = _audit(
            {
                "event": "rejected",
                "profile": profile,
                "verb": verb,
                "argument_count": len(arguments),
                "argument_digest": _audit_argument_digest(arguments),
                "reason": str(exc),
                "elevated": False,
            }
        )
        return {
            "success": False,
            "status": "command_rejected",
            "profile": profile,
            "error": str(exc),
            "audit_id": audit_id,
            "audit_logged": logged,
            "elevated": False,
        }

    digest = _request_digest(profile, verb, arguments, compiled.cwd)
    confirmed = False
    if profile in _CONFIRMABLE_PROFILES:
        if not confirm_token or not _consume_confirmation(confirm_token, digest):
            audit_id, logged = _audit(
                {
                    "event": "confirmation_required",
                    "profile": profile,
                    "verb": verb,
                    "argument_count": len(arguments),
                    "argument_digest": _audit_argument_digest(arguments),
                        "elevated": False,
                }
            )
            return {
                "success": False,
                "status": "confirmation_required",
                "profile": profile,
                "request_digest": digest[:16],
                "message": "call host_command_request_confirmation and pass its token",
                "audit_id": audit_id,
                "audit_logged": logged,
                "elevated": False,
            }
        confirmed = True

    environment = _sanitized_environment()
    started = time.monotonic()
    try:
        completed = _spawn(compiled.argv, compiled.cwd, environment, compiled.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated = _bound(_as_text(exc.stdout), MAX_STDOUT_CHARS)
        stderr, stderr_truncated = _bound(_as_text(exc.stderr), MAX_STDERR_CHARS)
        output_truncated = (
            stdout_truncated
            or stderr_truncated
            or bool(getattr(exc, "_jarvis_truncated", False))
        )
        audit_id, logged = _audit(
            {
                "event": "timeout",
                "truncated": output_truncated,
                "profile": profile,
                "verb": verb,
                "argument_count": len(arguments),
                "argument_digest": _audit_argument_digest(arguments),
                "elapsed_ms": elapsed_ms,
                "timeout_seconds": compiled.timeout_seconds,
                "confirmed": confirmed,
                "elevated": False,
            }
        )
        return {
            "success": False,
            "status": "timeout",
            "profile": profile,
            "verb": verb,
            "command": compiled.display,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": True,
            "truncated": output_truncated,
            "timeout_seconds": compiled.timeout_seconds,
            "elapsed_ms": elapsed_ms,
            "audit_id": audit_id,
            "audit_logged": logged,
            "elevated": False,
        }
    except OSError as exc:
        audit_id, logged = _audit(
            {
                "event": "launch_failed",
                "profile": profile,
                "verb": verb,
                "argument_count": len(arguments),
                "argument_digest": _audit_argument_digest(arguments),
                "reason": type(exc).__name__,
                "elevated": False,
            }
        )
        return {
            "success": False,
            "status": "execution_failed",
            "profile": profile,
            "error": type(exc).__name__,
            "audit_id": audit_id,
            "audit_logged": logged,
            "elevated": False,
        }

    elapsed_ms = int((time.monotonic() - started) * 1000)
    stdout, stdout_truncated = _bound(completed.stdout, MAX_STDOUT_CHARS)
    stderr, stderr_truncated = _bound(completed.stderr, MAX_STDERR_CHARS)
    capture_truncated = bool(getattr(completed, "_jarvis_truncated", False))
    output_truncated = stdout_truncated or stderr_truncated or capture_truncated
    success = completed.returncode == 0
    audit_id, logged = _audit(
        {
            "event": "executed",
            "profile": profile,
            "verb": verb,
            "argument_count": len(arguments),
            "argument_digest": _audit_argument_digest(arguments),
            "cwd": str(compiled.cwd),
            "exit_code": completed.returncode,
            "elapsed_ms": elapsed_ms,
            "truncated": output_truncated,
            "confirmed": confirmed,
            "elevated": False,
        }
    )
    logger.info(
        "Host ops profile=%s verb=%s exit=%s elapsed_ms=%s", profile, verb, completed.returncode, elapsed_ms
    )
    return {
        "success": success,
        "status": "completed" if success else "command_failed",
        "profile": profile,
        "verb": verb,
        "command": compiled.display,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": completed.returncode,
        "timed_out": False,
        "truncated": output_truncated,
        "elapsed_ms": elapsed_ms,
        "audit_id": audit_id,
        "audit_logged": logged,
        "elevated": False,
        "shell": False,
    }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def describe_profiles() -> dict[str, Any]:
    """Return the effective policy summary for agents and operators."""
    return {
        "success": True,
        "roots": [str(root) for root in allowed_roots()],
        "limits": {
            "list_depth": MAX_LIST_DEPTH,
            "list_entries": MAX_LIST_ENTRIES,
            "read_bytes": MAX_READ_BYTES,
            "read_lines": MAX_READ_LINES,
            "arguments": MAX_ARGUMENTS,
            "stdout_chars": MAX_STDOUT_CHARS,
            "stderr_chars": MAX_STDERR_CHARS,
            "timeout_seconds": [MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS],
        },
        "profiles": [
            {
                "name": "powershell_readonly",
                "verbs": sorted(_POWERSHELL_POLICIES),
                "shell": False,
                "elevated": False,
            },
            {
                "name": "git",
                "verbs": sorted(_GIT_POLICIES),
                "shell": False,
                "elevated": False,
            },
            {
                "name": "inspect_d",
                "verbs": sorted(_INSPECT_D_POLICIES),
                "targets": "D:\\ only",
                "shell": False,
                "elevated": False,
            },
        ],
        "confirmable_profiles": sorted(_CONFIRMABLE_PROFILES),
        "blocked_capabilities": [
            "filesystem writes",
            "package installation",
            "boot/partition changes",
            "ACL or ownership changes",
            "credential or secret access",
            "privilege elevation",
        ],
        "read_only": True,
    }
