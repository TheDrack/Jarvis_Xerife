"""Bounded read-only filesystem navigation for the authenticated Jarvis MCP tunnel.

This module deliberately does not invoke a shell, subprocess, Git, or arbitrary
executables. The supported command language is limited to pwd, cd, ls, and cat.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import re
import shlex
import stat
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_COMMAND_CHARS = 2048
MAX_OUTPUT_CHARS = 16_000
MAX_READ_BYTES = 64 * 1024
MAX_ENTRIES = 200

_FORBIDDEN_SYNTAX = re.compile(r"[\x00-\x1f;|&`$<>]")
_TEXT_SUFFIXES = frozenset(
    {
        ".txt", ".md", ".rst", ".py", ".ps1", ".sh", ".bat", ".cmd",
        ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
        ".service", ".socket", ".timer", ".log", ".sql", ".xml",
        ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".gitignore",
    }
)
_SPECIAL_TEXT_NAMES = frozenset({"readme", "license", "dockerfile", "makefile", "procfile"})
_SENSITIVE_NAMES = re.compile(
    r"(?i)^(?:"
    r"\.env(?:\..*)?|\.envrc|\.npmrc|\.netrc|\.git|\.git-credentials|"
    r"\.ssh|\.aws|\.azure|\.gnupg|\.kube|\.docker|\.pypirc|\.pgpass|\.my\.cnf|"
    r"\.password-store|\.terraform|\.vault|\.npm|\.config-credentials|"
    r"(?:.*[._-]|^)(?:kubeconfig|netrc|pgpass|htpasswd|master\.pass)(?:\..*)?|"
    r"credentials?(?:[._-].*)?|secrets?(?:[._-].*)?|tokens?(?:[._-].*)?|"
    r"passwords?(?:[._-].*)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\..*)?|authorized_keys|"
    r".*\.(?:pem|p12|pfx|key|jks|keystore|ppk|p8|tfstate|tfstate\..*)"
    r")$"
)
_SENSITIVE_PREFIXES = (
    (".config", "gh"),
    (".config", "gcloud"),
    (".config", "containers"),
    (".config", "glab-cli"),
    (".config", "github-copilot"),
    (".config", "composer"),
    (".config", "age"),
    (".config", "ngrok"),
    (".config", "rclone"),
    (".config", "op"),
    (".config", "sops"),
    (".config", "hub"),
    (".config", "podman"),
    (".local", "share", "keyrings"),
    (".terraform.d",),
    ("appdata", "roaming", "github cli"),
    ("appdata", "local", "github cli"),
    ("appdata", "roaming", "microsoft", "credentials"),
    ("appdata", "local", "microsoft", "credentials"),
    ("appdata", "roaming", "filezilla"),
)

_SECRET_CONTENT = re.compile(
    rb"(?im)(?:"
    rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    rb"-----BEGIN PGP PRIVATE KEY BLOCK-----|"
    rb"AGE-SECRET-KEY-|"
    rb"(?<![A-Z0-9_-])[A-Z0-9_.-]*(?:api[_-]?key|access[_-]?key|"
    rb"access[_-]?token|refresh[_-]?token|id[_-]?token|session[_-]?token|"
    rb"client[_-]?secret|private[_-]?key|signing[_-]?key|password|passwd|"
    rb"passphrase|token|secret|credential|authorization|oauth[_-]?token)"
    rb"[A-Z0-9_.-]*[\"']?\s*[:=]\s*[\"']?(?:basic\s+)?[^\s,;\"'}]{4,}|"
    rb"(?<![A-Z0-9_-])[\"']?key[\"']?\s*[:=]\s*(?:\"[^\"\r\n]{16,}\"|'[^'\r\n]{16,}'|[A-Za-z0-9+/=_-]{16,})|"
    rb"^[ \t]*[\"']?[A-Z0-9_.-]*(?:password|passwd|token|secret|credential|api[_-]?key)"
    rb"[A-Z0-9_.-]*[\"']?\s*:\s*[|>][-+]?\s*(?:\r?\n[ \t]+\S+)+|"
    rb"\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*|"
    rb"[a-z][a-z0-9+.-]*://[^/\s:@\"']*:[^\s/\"']+@|"
    rb"(?:client[_-]?key[_-]?data|certificate[_-]?authority[_-]?data|account[_-]?key|"
    rb"bindpw|bind[_-]?password|ansible[_-]?ssh[_-]?pass|smtp[_-]?pass(?:word)?|"
    rb"database[_-]?url|connection[_-]?string)[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]{4,}|"
    rb"(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]*key[_-]?data[\"']?\s*[:=]\s*[A-Za-z0-9+/=]{32,}|"
    rb"(?<![A-Za-z0-9_.-])[\"']?(?:pass|pwd)[\"']?\s*[:=]\s*[\"']?(?![Tt]rue|[Ff]alse|[Nn]one|[Nn]ull|\d)[^\s,;\"'}]{4,}|"
    rb"(?<![A-Za-z0-9])hvs\.[A-Za-z0-9_-]{16,}|"
    rb"(?<![A-Za-z0-9])sk_(?:live|test)_[A-Za-z0-9]{16,}|"
    rb"\$(?:apr1|1|5|6|y)\$[^:\s]{8,}|"
    rb"(?i:^[ \t]*(?:insert[ \t]+into|update|replace[ \t]+into)\b[^\r\n]*\b(?:password|passwd|pwd|secret|token|api[_-]?key)\b)|"
    rb"<\s*(?:password|token|secret|api[_-]?key)\b[^>]*>\s*[^<]{4,}</\s*"
    rb"(?:password|token|secret|api[_-]?key)\s*>|"
    rb"(?<![A-Z0-9])(?:eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    rb"gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|"
    rb"glpat-[A-Za-z0-9_-]{16,}|xox[abposr]-[A-Za-z0-9-]{10,}|"
    rb"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}))"
)


def _is_reparse_point(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _is_sensitive_path(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    if any(_SENSITIVE_NAMES.fullmatch(part) for part in parts):
        return True
    for prefix in _SENSITIVE_PREFIXES:
        width = len(prefix)
        if any(parts[index:index + width] == prefix for index in range(len(parts) - width + 1)):
            return True
    return False


class ShellNavigator:
    """Stateful filesystem navigator constrained to explicit directory roots."""

    def __init__(
        self,
        *,
        allowed_roots: list[str | Path] | None = None,
        initial_directory: str | Path | None = None,
        max_entries: int = MAX_ENTRIES,
        max_read_bytes: int = MAX_READ_BYTES,
    ) -> None:
        if allowed_roots is None:
            roots = [Path(__file__).resolve().parents[3]]
            configured = os.environ.get("JARVIS_SHELL_ALLOWED_ROOTS", "")
            roots.extend(Path(item) for item in configured.split(os.pathsep) if item.strip())
        else:
            roots = [Path(item) for item in allowed_roots]

        resolved_roots: list[Path] = []
        for root in roots:
            try:
                resolved = root.expanduser().resolve(strict=True)
            except OSError:
                continue
            if resolved.is_dir() and resolved not in resolved_roots:
                resolved_roots.append(resolved)
        if not resolved_roots:
            raise ValueError("at least one existing allowed directory is required")

        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise ValueError("max_entries must be an integer")
        if isinstance(max_read_bytes, bool) or not isinstance(max_read_bytes, int):
            raise ValueError("max_read_bytes must be an integer")

        self.allowed_roots = tuple(resolved_roots)
        self.max_entries = min(max(max_entries, 1), MAX_ENTRIES)
        self.max_read_bytes = min(max(max_read_bytes, 1), MAX_READ_BYTES)
        initial = Path(initial_directory) if initial_directory is not None else self.allowed_roots[0]
        if not initial.is_absolute():
            initial = self.allowed_roots[0] / initial
        self._initial_directory = self._resolve(str(initial))
        if not self._initial_directory.is_dir():
            raise ValueError("initial directory must be a directory")
        self._cwd = self._initial_directory
        self._lock = threading.RLock()

    @property
    def cwd(self) -> Path:
        with self._lock:
            return self._cwd

    def _is_allowed(self, path: Path) -> bool:
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _resolve(self, raw_path: str | None, *, base: Path | None = None) -> Path:
        raw = "." if raw_path is None or raw_path == "" else str(raw_path)
        if "\x00" in raw or raw.startswith(("~", "\\\\", "//")):
            raise PermissionError("path syntax is not permitted")
        normalized = raw.replace("\\", "/")
        if any(part == ".." for part in normalized.split("/")):
            raise PermissionError("parent traversal is not permitted")
        self._validate_windows_path_syntax(raw)

        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (base if base is not None else self.cwd) / candidate
        candidate = Path(os.path.abspath(candidate))

        matching_root = next(
            (root for root in self.allowed_roots if self._is_lexically_within(candidate, root)),
            None,
        )
        if matching_root is None:
            raise PermissionError("path is outside allowed roots")

        relative_parts = candidate.relative_to(matching_root).parts
        current = matching_root
        for part in relative_parts:
            current = current / part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                raise FileNotFoundError("path does not exist") from None
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
                raise PermissionError("symlink and reparse-point paths are not permitted")

        resolved = candidate.resolve(strict=True)
        if not self._is_allowed(resolved):
            raise PermissionError("path is outside allowed roots")
        return resolved

    @staticmethod
    def _validate_windows_path_syntax(raw: str) -> None:
        if os.name != "nt":
            return
        normalized = raw.replace("/", "\\")
        drive, tail = os.path.splitdrive(normalized)
        if drive and not Path(normalized).is_absolute():
            raise PermissionError("drive-relative paths are not permitted")
        for component in tail.split("\\"):
            if not component or component in {".", ".."}:
                continue
            if component.endswith((".", " ")):
                raise PermissionError("Windows trailing-dot and trailing-space aliases are not permitted")
            if ":" in component:
                raise PermissionError("NTFS alternate data streams are not permitted")
            device = component.split(".", 1)[0].casefold().translate(
                str.maketrans("\u00b9\u00b2\u00b3", "123")
            )
            if device in {"con", "prn", "aux", "nul"} or re.fullmatch(
                r"(?:com|lpt)[1-9]", device
            ):
                raise PermissionError("reserved Windows device names are not permitted")

    @staticmethod
    def _is_lexically_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _tokens(command: str) -> list[str]:
        if not isinstance(command, str):
            raise ValueError("command must be text")
        normalized = command.strip()
        if not normalized or len(normalized) > MAX_COMMAND_CHARS:
            raise ValueError(f"command must contain 1 to {MAX_COMMAND_CHARS} characters")
        if _FORBIDDEN_SYNTAX.search(normalized):
            raise ValueError("shell operators and control characters are not permitted")
        try:
            lexer = shlex.shlex(normalized, posix=False)
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        except ValueError:
            raise ValueError("command quoting is invalid") from None
        if not tokens:
            raise ValueError("command is empty")
        return [
            token[1:-1]
            if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}
            else token
            for token in tokens
        ]

    def _failure(self, status: str, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "status": status,
            "message": message,
            "content": "",
            "output": "",
            "cwd": str(self.cwd),
            "read_only": True,
        }

    def _list_directory(
        self, raw_path: str | None, *, base: Path | None = None
    ) -> dict[str, Any]:
        directory = self._resolve(raw_path, base=base)
        if _is_sensitive_path(directory):
            return self._failure("sensitive_path_blocked", "sensitive directories cannot be listed")
        if not directory.is_dir():
            return self._failure("not_a_directory", "path is not a directory")

        entries: list[dict[str, Any]] = []
        filtered = 0
        truncated = False
        with os.scandir(directory) as scanner:
            children = list(itertools.islice(scanner, self.max_entries + 1))
        if len(children) > self.max_entries:
            truncated = True
        children = sorted(children[: self.max_entries], key=lambda entry: entry.name.casefold())

        for entry in children:
            candidate = Path(entry.path)
            if _is_sensitive_path(candidate):
                filtered += 1
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                metadata = None
            if entry.is_symlink() or (metadata is not None and _is_reparse_point(metadata)):
                kind = "symlink"
            elif metadata is not None and stat.S_ISDIR(metadata.st_mode):
                kind = "directory"
            elif metadata is not None and stat.S_ISREG(metadata.st_mode):
                kind = "file"
            else:
                kind = "other"
            entries.append(
                {
                    "name": entry.name,
                    "kind": kind,
                    "size": metadata.st_size if metadata is not None and kind == "file" else None,
                    "hidden": entry.name.startswith("."),
                }
            )

        output = json.dumps(entries, ensure_ascii=True, separators=(",", ":"))
        while len(output) > MAX_OUTPUT_CHARS and entries:
            entries.pop()
            truncated = True
            output = json.dumps(entries, ensure_ascii=True, separators=(",", ":"))
        return {
            "success": True,
            "status": "listed",
            "path": str(directory),
            "cwd": str(self.cwd),
            "entries": entries,
            "entry_count": len(entries),
            "filtered_sensitive_entries": filtered,
            "truncated": truncated,
            "output": output,
            "read_only": True,
        }

    def _read_text(self, raw_path: str, *, base: Path | None = None) -> dict[str, Any]:
        target = self._resolve(raw_path, base=base)
        if _is_sensitive_path(target):
            return self._failure("sensitive_file_blocked", "credential stores and sensitive files are blocked")
        if not target.is_file():
            return self._failure("not_a_file", "path is not a regular file")
        if target.suffix.casefold() not in _TEXT_SUFFIXES and target.name.casefold() not in _SPECIAL_TEXT_NAMES:
            return self._failure("unsupported_file_type", "file extension is not allowlisted")

        try:
            total_bytes = target.stat().st_size
            with target.open("rb") as handle:
                data = handle.read(self.max_read_bytes + 1)
        except OSError:
            return self._failure("read_failed", "file could not be read")

        if b"\x00" in data[:8192]:
            return self._failure("binary_file", "binary content is not returned")
        truncated = len(data) > self.max_read_bytes
        if truncated:
            data = data[: self.max_read_bytes]
            final_newline = data.rfind(b"\n")
            data = data[: final_newline + 1] if final_newline >= 0 else b""
        if _SECRET_CONTENT.search(data):
            return self._failure("secret_content_blocked", "file contains credential-shaped material")

        content = data.decode("utf-8", errors="replace")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        if len(content) > MAX_OUTPUT_CHARS:
            content = content[:MAX_OUTPUT_CHARS]
            final_newline = content.rfind("\n")
            content = content[: final_newline + 1] if final_newline >= 0 else ""
            truncated = True

        return {
            "success": True,
            "status": "read",
            "path": str(target),
            "cwd": str(self.cwd),
            "content": content,
            "output": content,
            "bytes_returned": len(content.encode("utf-8")),
            "total_bytes": total_bytes,
            "truncated": truncated,
            "read_only": True,
        }

    def execute(self, command: str) -> dict[str, Any]:
        """Execute one command from the pwd/cd/ls/cat allowlist; never starts a process."""
        try:
            tokens = self._tokens(command)
        except ValueError as exc:
            return self._failure("command_rejected", str(exc))

        verb, *arguments = tokens
        try:
            if verb == "pwd" and not arguments:
                with self._lock:
                    current = str(self._cwd)
                return {
                    "success": True,
                    "status": "ok",
                    "cwd": current,
                    "output": current,
                    "read_only": True,
                }

            if verb == "cd" and len(arguments) <= 1:
                with self._lock:
                    destination = (
                        self._initial_directory
                        if not arguments
                        else self._resolve(arguments[0], base=self._cwd)
                    )
                    if not destination.is_dir():
                        return self._failure("not_a_directory", "path is not a directory")
                    self._cwd = destination
                    current = str(self._cwd)
                return {
                    "success": True,
                    "status": "directory_changed",
                    "cwd": current,
                    "output": current,
                    "read_only": True,
                }

            with self._lock:
                base = self._cwd
            if verb == "ls" and len(arguments) <= 1:
                return self._list_directory(arguments[0] if arguments else None, base=base)
            if verb == "cat" and len(arguments) == 1:
                return self._read_text(arguments[0], base=base)
            return self._failure(
                "command_rejected",
                "only pwd, cd [path], ls [path], and cat <text-file> are supported",
            )
        except PermissionError:
            return self._failure("path_rejected", "path is outside the permitted filesystem scope")
        except FileNotFoundError:
            return self._failure("path_rejected", "path does not exist")
        except OSError:
            return self._failure("filesystem_error", "filesystem operation failed")

def register_shell_navigation_tools(
    mcp: Any, *, navigator: ShellNavigator | None = None
) -> tuple[str, ...]:
    """Register shell_navigate only after an explicit machine-owner opt-in."""
    enabled = os.environ.get("JARVIS_SHELL_NAVIGATION_ENABLED", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        logger.info(
            "Shell navigation is disabled; set JARVIS_SHELL_NAVIGATION_ENABLED=1 to opt in"
        )
        return ()

    try:
        active_navigator = navigator or ShellNavigator()
    except (OSError, ValueError) as exc:
        logger.warning("Shell navigation could not initialize: %s", type(exc).__name__)
        return ()

    @mcp.tool(name="shell_navigate")
    def shell_navigate(command: str) -> dict[str, Any]:
        """Navigate allowed directories using pwd/cd/ls/cat only; no shell or Git execution."""
        from app.adapters.infrastructure.session_authorization import (
            SESSION_GATEWAY,
            SessionAuthorizationError,
        )

        normalized = command.strip().split(maxsplit=1)[0].casefold() if command.strip() else ""
        capability = "host.fs.read" if normalized == "cat" else "host.fs.list"
        try:
            authorization = SESSION_GATEWAY.require(capability)
        except SessionAuthorizationError as exc:
            return {
                "success": False,
                "status": "session_authorization_denied",
                "error": str(exc),
                "required_capability": capability,
            }
        result = active_navigator.execute(command)
        return {
            **result,
            "session_id": authorization["session_id"],
            "session_profile": authorization["profile"],
        }

    return ("shell_navigate",)
