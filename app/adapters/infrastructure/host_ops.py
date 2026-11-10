"""Read-only host operations exposed through the authenticated Jarvis MCP tunnel.

This module complements :mod:`app.adapters.infrastructure.secure_shell_executor`.
The existing executor validates one PowerShell *string* against an AST allowlist;
this module never builds a shell string from caller input. It accepts a profile
name, a verb and a structured argv, validates every token against a per-verb
policy, and launches the process with ``shell=False``.

Boundaries enforced here:

* every filesystem path must resolve inside an explicit allowed root (repository
  root plus ``D:\\`` on Windows, or ``JARVIS_HOST_OPS_ROOTS``); ``..`` segments
  are rejected before resolution and symlinks/junctions are resolved and
  re-checked, so a link cannot escape a root;
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
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60

PROFILES = ("powershell_readonly", "git", "pytest", "inspect_d")


class PathNotAllowed(ValueError):
    """Raised when a path is outside the allowed roots or looks like a secret."""


# --------------------------------------------------------------------------- #
# Roots and path resolution
# --------------------------------------------------------------------------- #
def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _norm(value: Path | str) -> str:
    return os.path.normcase(str(value)).rstrip("\\/")


def _is_within(path: Path, root: Path) -> bool:
    normalized_path = _norm(path)
    normalized_root = _norm(root)
    return normalized_path == normalized_root or normalized_path.startswith(
        normalized_root + os.sep
    )


def _reject_secret_name(path: Path) -> None:
    for part in path.parts:
        lowered = part.casefold()
        if lowered in _SECRET_DIRECTORIES:
            raise PathNotAllowed("path component is a credential directory")
    if _SECRET_FILE_NAME.match(path.name):
        raise PathNotAllowed("file name looks like a credential store")


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
    if ":" in text and not re.match(r"^[A-Za-z]:[\\/]", text):
        raise PathNotAllowed("provider-qualified and drive-relative paths are not accepted")
    if re.split(r"[\\/]+", text).count("..") or ".." in re.split(r"[\\/]+", text):
        raise PathNotAllowed("parent traversal is not permitted")

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = _repository_root() / candidate
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
    {".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker", ".password-store", ".git"}
)
_SECRET_FILE_NAME = re.compile(
    r"""(?ix)^(
        .*\.env(\..*)?
        |\.npmrc|\.pypirc|\.netrc|\.git-credentials
        |id_(rsa|dsa|ecdsa|ed25519)(\..*)?
        |kubeconfig(\..*)?|admin\.conf
        |credentials(\..*)?
        |secrets?(\.(json|ya?ml|txt|toml))?
        |token(s)?\.(json|txt)
        |.*\.(pem|key|pfx|p12|jks|keystore|kdbx)
        |.*\.(tfvars|tfstate)
        |.*\.(sqlite|sqlite3|db)
    )$"""
)
_PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_BINARY_PROBE = 8192


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #
_REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{8,}=*"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}|\bnpm_[A-Za-z0-9]{16,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|APKA|AROA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    (
        re.compile(
            r"(?i)((?:client[_-]?key[_-]?data|certificate[_-]?authority[_-]?data|account[_-]?key)\s*[:=]\s*)(\S{8,})"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"""([a-z][a-z0-9+.-]*://[^/\s:@"']*:)([^@\s/"']+)@"""),
        r"\1[REDACTED]@",
    ),
    (
        re.compile(
            r"""(?i)(\b[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|SIGNING[_-]?KEY|AUTH[_-]?TOKEN|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|CLIENT[_-]?SECRET|SERVICE[_-]?ROLE[_-]?KEY|SECRET[A-Z0-9_-]*|TOKEN|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL)[A-Z0-9_]*\s*[:=]\s*["']?)([^"'\s,;}]+)"""
        ),
        r"\1[REDACTED]",
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


def _entry_kind(entry: os.DirEntry[str]) -> str:
    if entry.is_symlink():
        return "symlink"
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    if is_junction(entry.path):
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
            children = sorted(
                os.scandir(current), key=lambda item: (not item.is_dir(), item.name.casefold())
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
            if entry.name.casefold() in _SECRET_DIRECTORIES or _SECRET_FILE_NAME.match(entry.name):
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
    if validator == "expression":
        if not _EXPRESSION_VALIDATOR.match(value):
            raise ValueError("invalid pytest selection expression")
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


def _powershell_quote(value: str) -> str:
    if "'" in value or "`" in value:
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
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        environment.update(extra)
    return environment


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
    if profile in {"git", "pytest"} and not _is_within(workdir, _repository_root()):
        raise PathNotAllowed("git and pytest must run inside the repository root")

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
        argv = ("git", "--no-pager", verb, *[token for pair in parsed for token in pair if token])
        return CompiledCommand(profile, verb, argv, workdir, timeout_seconds, joined)

    if profile == "pytest":
        return _compile_pytest(verb, arguments, workdir, timeout_seconds)

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


def _compile_pytest(
    verb: str, arguments: Sequence[str], workdir: Path, timeout_seconds: int
) -> CompiledCommand:
    if verb not in {"run", "tests"}:
        raise ValueError("pytest verb must be 'run'")
    if len(arguments) > 6:
        raise ValueError("at most 6 pytest arguments are accepted")
    targets: list[str] = []
    extra: list[str] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if not isinstance(token, str) or not token:
            raise ValueError("pytest arguments must be non-empty strings")
        if token.startswith("-") and token not in {"-x", "-q", "-k", "--maxfail"}:
            raise ValueError(f"pytest option {token} is not allowlisted")
        if token in {"-x", "-q"}:
            extra.append(token)
            index += 1
            continue
        if token in {"-k", "--maxfail"}:
            if index + 1 >= len(arguments):
                raise ValueError(f"{token} requires a value")
            value = arguments[index + 1]
            _validate_argument_value(
                "expression" if token == "-k" else "integer", value
            )
            extra.extend([token, value])
            index += 2
            continue
        target = resolve_path(token, must_exist=True)
        tests_root = (_repository_root() / "tests").resolve()
        if not _is_within(target, tests_root):
            raise PathNotAllowed("pytest targets must live under tests/")
        if target.suffix != ".py" and not target.is_dir():
            raise ValueError("pytest targets must be Python files or directories")
        targets.append(str(target))
        index += 1
    if not targets:
        raise ValueError("at least one tests/ target is required")
    executable = sys.executable
    if Path(executable).name.casefold() not in {"python", "python.exe", "python3", "python3.exe"}:
        raise RuntimeError("pytest profile requires a Python interpreter")
    argv = (
        executable,
        "-m",
        "pytest",
        *targets,
        "-q",
        "-p",
        "no:cacheprovider",
        *extra,
    )
    return CompiledCommand(
        "pytest", "run", argv, workdir, timeout_seconds, "pytest " + " ".join(targets)
    )


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
def _audit_path() -> Path:
    configured = os.environ.get("JARVIS_HOST_OPS_AUDIT_LOG", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "jarvis" / "host_ops_audit.jsonl"


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
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
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
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        env=dict(environment),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        shell=False,
        check=False,
    )


def _bound(value: str | None, limit: int) -> tuple[str, bool]:
    redacted, _ = redact(value or "")
    if _PRIVATE_KEY_BLOCK.search(redacted):
        return "[WITHHELD: output contained a private key block]", True
    return redacted[:limit], len(redacted) > limit


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
                "arguments": arguments,
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
    except (ValueError, RuntimeError) as exc:
        audit_id, logged = _audit(
            {
                "event": "rejected",
                "profile": profile,
                "verb": verb,
                "arguments": arguments,
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
                    "arguments": arguments,
                    "digest": digest[:16],
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
        stdout, _ = _bound(_as_text(exc.stdout), MAX_STDOUT_CHARS)
        stderr, _ = _bound(_as_text(exc.stderr), MAX_STDERR_CHARS)
        audit_id, logged = _audit(
            {
                "event": "timeout",
                "profile": profile,
                "verb": verb,
                "arguments": arguments,
                "digest": digest[:16],
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
                "arguments": arguments,
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
    success = completed.returncode == 0
    audit_id, logged = _audit(
        {
            "event": "executed",
            "profile": profile,
            "verb": verb,
            "arguments": arguments,
            "digest": digest[:16],
            "cwd": str(compiled.cwd),
            "exit_code": completed.returncode,
            "elapsed_ms": elapsed_ms,
            "truncated": stdout_truncated or stderr_truncated,
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
        "truncated": stdout_truncated or stderr_truncated,
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
                "name": "pytest",
                "verbs": ["run"],
                "targets": "tests/ only",
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
