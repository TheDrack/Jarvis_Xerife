"""Bounded, read-only shell navigation exposed over the authenticated MCP tunnel.

This is a navigation console, not an unrestricted shell. It supports directory
navigation, bounded text reads, metadata listings, and a small read-only Git
command set. Commands are parsed into argv and never passed to a shell.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import stat
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_COMMAND_CHARS = 2048
MAX_OUTPUT_CHARS = 16_000
MAX_READ_BYTES = 64 * 1024
MAX_ENTRIES = 200
MAX_TIMEOUT_SECONDS = 15

_FORBIDDEN_SYNTAX = re.compile(r"[\x00\r\n;|&`$<>{}()]")
_SENSITIVE_PART = re.compile(
    r"(?i)^(?:"
    r"\.env(?:\..*)?|\.envrc|\.npmrc|\.netrc|\.git-credentials|"
    r"\.ssh|\.aws|\.azure|\.gnupg|\.kube|\.docker|"
    r"\.password-store|\.terraform|\.vault|\.m2|\.yarnrc\.yml|\.pgpass|\.my\.cnf|\.pypirc|"
    r"\.?credentials?(?:[._-].*)?|\.?secrets?(?:[._-].*)?|"
    r"\.?tokens?(?:[._-].*)?|\.?passwords?(?:[._-].*)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\..*)?|authorized_keys|"
    r".*\.(?:pem|p12|pfx|key|jks|keystore|ppk|p8)"
    r")$"
)
_SENSITIVE_PATH_PREFIXES = (
    (".config", "gcloud"),
    (".config", "gh"),
    (".config", "containers"),
    (".config", "rclone"),
    (".config", "glab-cli"),
    (".config", "github-copilot"),
    (".config", "composer"),
    (".config", "age"),
    (".config", "ngrok"),
    (".config", "op"),
    (".config", "sops"),
    (".config", "hub"),
    (".config", "podman"),
    (".gem", "credentials"),
    (".local", "share", "keyrings"),
    ("appdata", "roaming", "code", "user", "globalstorage"),
    ("appdata", "local", "github cli"),
    ("appdata", "roaming", "github cli"),
    ("appdata", "roaming", "microsoft", "credentials"),
    ("appdata", "local", "microsoft", "credentials"),
    (".config", "filezilla"),
    (".terraform.d",),
    (".local", "share", "powershell"),
    ("appdata", "roaming", "filezilla"),
    ("appdata", "roaming", "microsoft", "windows", "powershell"),
    ("appdata", "local", "microsoft", "windows", "powershell"),
)


def _is_sensitive_path(path: Path) -> bool:
    parts = tuple(part.casefold() for part in path.parts)
    if any(_SENSITIVE_PART.fullmatch(part) for part in parts):
        return True
    for prefix in _SENSITIVE_PATH_PREFIXES:
        width = len(prefix)
        if any(parts[index:index + width] == prefix for index in range(len(parts) - width + 1)):
            return True
    return False


def _git_repository_within(root: Path, cwd: Path) -> tuple[Path, Path]:
    """Find a normal repository without allowing Git's upward discovery past root."""
    current = cwd
    while True:
        marker = current / ".git"
        if marker.is_file():
            raise PermissionError("Git worktrees and external gitdir pointers are not permitted")
        if marker.is_symlink():
            raise PermissionError("Git metadata symlinks are not permitted")
        if marker.is_dir():
            if (marker / "commondir").exists() or (marker / "objects" / "info" / "alternates").exists():
                raise PermissionError("shared Git metadata outside the repository root is not permitted")
            return current, marker
        if current == root:
            break
        current = current.parent
    raise PermissionError("no Git repository exists inside the allowed root")


def _repository_config_files(git_dir: Path) -> list[Path]:
    """Return every repository config file Git may consult."""
    files = [git_dir / "config"]
    worktree_config = git_dir / "config.worktree"
    if worktree_config.exists() or worktree_config.is_symlink():
        files.append(worktree_config)
    return files


_EXECUTABLE_GIT_KEYS = {
    "core": frozenset({"fsmonitor", "hookspath", "sshcommand", "askpass", "pager", "worktree", "attributesfile"}),
    "diff": frozenset({"external", "textconv", "command"}),
    "filter": frozenset({"clean", "smudge", "process"}),
    "credential": frozenset({"helper"}),
    "gpg": frozenset({"program"}),
    "merge": frozenset({"driver"}),
    "submodule": frozenset({"update"}),
}


def _parse_git_config(raw: str) -> list[tuple[str, str]]:
    """Conservatively parse section headers and keys, including same-line entries."""
    entries: list[tuple[str, str]] = []
    section = ""
    for line in raw.lstrip("\ufeff").splitlines():
        value = line.strip()
        while value.startswith("["):
            close = value.find("]")
            if close < 0:
                raise ValueError("repository Git config is not parseable")
            header = value[1:close].strip()
            section = header.split(None, 1)[0].strip('"').casefold()
            value = value[close + 1:].strip()
        if not value or value.startswith(("#", ";")):
            continue
        key = value.split("=", 1)[0].strip().strip('"').casefold()
        if not key or not key.replace("-", "").isalnum():
            raise ValueError("repository Git config is not parseable")
        entries.append((section, key))
    return entries


def _assert_trusted_git_config(git_dir: Path) -> None:
    """Reject config capable of including files or launching executable helpers."""
    for config in _repository_config_files(git_dir):
        if not config.exists():
            continue
        if config.is_symlink() or config.stat().st_size > 128 * 1024:
            raise ValueError("repository Git config is not safe to inspect")
        raw = config.read_text(encoding="utf-8", errors="strict")
        for section, key in _parse_git_config(raw):
            if section == "include" or section.startswith("includeif"):
                raise ValueError("repository Git config includes external configuration")
            if key in _EXECUTABLE_GIT_KEYS.get(section, frozenset()):
                raise ValueError("repository Git config contains an executable helper setting")

_SECRET_CONTENT = re.compile(
    rb"(?i)(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|\"auths\"\s*:|oauth[_-]?token|access[_-]?token|refresh[_-]?token|id[_-]?token|session[_-]?token|client[-_]?secret|private[_-]?key|password\s*[:=]|client[-_]?key[-_]?data|"
    rb"certificate[-_]?authority[-_]?data|account[-_]?key|AGE-SECRET-KEY-|"
    rb"gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{16,}|"
    rb"xox[abposr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|"
    rb"AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|"
    rb"<\s*(?:password|token|secret|api[_-]?key)\b[^>]*>\s*[^<]{4,}</\s*(?:password|token|secret|api[_-]?key)\s*>)"
)


_TEXT_SUFFIXES = {
    ".txt", ".md", ".rst", ".py", ".ps1", ".sh", ".bat", ".cmd",
    ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".service", ".socket", ".timer", ".log", ".sql", ".xml",
    ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".gitignore",
}


_SPECIAL_TEXT_NAMES = {"readme", "license", "dockerfile", "makefile", "procfile"}


def _redact_text(value: str) -> str:
    """Redact provider tokens, key material, URL userinfo and credential assignments."""
    value = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", value)
    value = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(
        r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"glpat-[A-Za-z0-9_-]{16,}|xox[abposr]-[A-Za-z0-9-]{10,}|"
        r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|"
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})",
        "[REDACTED_SECRET]",
        value,
    )
    value = re.sub(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s]+@", r"\1[REDACTED]@", value)
    return re.sub(
        r"""(?i)(["']?[A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?key|secret[_-]?key|private[_-]?key|client[_-]?secret|secret|passwd|password|passphrase|pwd|token|credential|authorization|auth|pat)["']?\s*[:=]\s*["']?)[^"'\s,}]+""",
        r"\1[REDACTED]",
        value,
    )


_GIT_SIMPLE_ARGS = {
    ("status",): ["status"],
    ("status", "--short", "--branch"): ["status", "--short", "--branch"],
    ("remote", "-v"): ["remote", "-v"],
    ("branch", "--show-current"): ["branch", "--show-current"],
    ("branch", "--list"): ["branch", "--list"],
    ("diff", "--stat"): ["diff", "--stat"],
    ("diff", "--name-only"): ["diff", "--name-only"],
    ("diff", "--cached", "--stat"): ["diff", "--cached", "--stat"],
    ("diff", "--cached", "--name-only"): ["diff", "--cached", "--name-only"],
    ("show", "--stat", "--oneline", "-1"): ["show", "--stat", "--oneline", "-1"],
    ("ls-files",): ["ls-files"],
    ("rev-parse", "--show-toplevel"): ["rev-parse", "--show-toplevel"],
    ("rev-parse", "--abbrev-ref", "HEAD"): ["rev-parse", "--abbrev-ref", "HEAD"],
    ("rev-parse", "HEAD"): ["rev-parse", "HEAD"],
}


class ShellNavigator:
    """Stateful, bounded navigation over explicitly allowed filesystem roots."""

    def __init__(
        self,
        *,
        allowed_roots: list[str | Path] | None = None,
        initial_directory: str | Path | None = None,
        max_entries: int = MAX_ENTRIES,
        max_read_bytes: int = MAX_READ_BYTES,
    ) -> None:
        if allowed_roots is None:
            # Default to the repository only. Additional roots require an explicit
            # operator opt-in through JARVIS_SHELL_ALLOWED_ROOTS.
            roots = [Path(__file__).resolve().parents[3]]
            configured = os.environ.get("JARVIS_SHELL_ALLOWED_ROOTS", "")
            roots.extend(Path(item) for item in configured.split(os.pathsep) if item.strip())
        else:
            roots = [Path(item) for item in allowed_roots]

        self.allowed_roots = tuple(
            dict.fromkeys(root.expanduser().resolve() for root in roots if root.exists() and root.is_dir())
        )
        if not self.allowed_roots:
            raise ValueError("at least one existing allowed directory is required")

        self.max_entries = min(max(int(max_entries), 1), MAX_ENTRIES)
        self.max_read_bytes = min(max(int(max_read_bytes), 1), MAX_READ_BYTES)
        candidate = Path(initial_directory).expanduser() if initial_directory is not None else self.allowed_roots[0]
        resolved = candidate.resolve()
        if not self._is_allowed(resolved):
            raise ValueError("initial directory is outside allowed roots")
        if not resolved.is_dir():
            raise ValueError("initial directory must be a directory")
        self._cwd = resolved
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

    @staticmethod
    def _tokens(command: str) -> list[str]:
        if not isinstance(command, str):
            raise ValueError("command must be a string")
        normalized = command.strip()
        if not normalized or len(normalized) > MAX_COMMAND_CHARS:
            raise ValueError(f"command must contain 1 to {MAX_COMMAND_CHARS} characters")
        if _FORBIDDEN_SYNTAX.search(normalized):
            raise ValueError("shell operators, variables and multiline syntax are not permitted")
        lexer = shlex.shlex(normalized, posix=False)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
        return [
            token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'} else token
            for token in tokens
        ]

    def _resolve(self, raw_path: str | None, *, must_exist: bool = True) -> Path:
        raw = "" if raw_path is None else str(raw_path)
        normalized = raw.replace("/", "\\")
        if raw.startswith(("\\\\", "//")) or normalized.startswith("\\\\"):
            raise PermissionError("UNC and device paths are not permitted")

        candidate = self.cwd if not raw_path else Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        candidate = Path(os.path.abspath(candidate))
        current = Path(candidate.anchor)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for part in candidate.parts[1:]:
            current = current / part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & reparse_point:
                raise PermissionError("symlink and reparse-point paths are not permitted")
        resolved = candidate.resolve(strict=must_exist)
        if not self._is_allowed(resolved):
            raise PermissionError("path is outside allowed roots")
        return resolved

    def _git_argv(self, args: list[str]) -> list[str]:
        if tuple(args) in _GIT_SIMPLE_ARGS:
            return ["git", *_GIT_SIMPLE_ARGS[tuple(args)]]
        if len(args) == 3 and args[0] == "log" and args[1] == "--oneline" and re.fullmatch(r"-n(?:[1-9]|[12][0-9]|30)", args[2]):
            return ["git", "log", "--oneline", args[2]]
        if len(args) == 3 and args[0] == "log" and re.fullmatch(r"-n(?:[1-9]|[12][0-9]|30)", args[1]) and args[2] == "--oneline":
            return ["git", "log", args[1], "--oneline"]
        if len(args) == 4 and args[0] == "log" and args[1] == "--oneline" and args[2] == "-n" and re.fullmatch(r"[1-9]|[12][0-9]|30", args[3]):
            return ["git", "log", "--oneline", "-n", args[3]]
        raise ValueError("Git command is not in the read-only allowlist")

    def execute(self, command: str, *, timeout_seconds: int = 10) -> dict[str, Any]:
        """Execute one supported navigation command and return bounded output."""
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            return {"success": False, "status": "invalid_timeout", "output": ""}
        if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
            return {"success": False, "status": "invalid_timeout", "output": ""}

        try:
            tokens = self._tokens(command)
            verb = tokens[0].casefold()
            args = tokens[1:]
            with self._lock:
                if verb in {"help", "?"} and not args:
                    output = (
                        "Commands: pwd | cd [path] | ls [path] | cat <text-file> | "
                        "git status [--short --branch] | git remote -v | git branch --show-current | "
                        "git log --oneline -nN | git diff --stat|--name-only | git ls-files | help. "
                        "Read-only; paths are restricted to configured roots."
                    )
                    return self._result(output)

                if verb == "pwd" and not args:
                    return self._result(str(self._cwd))

                if verb == "cd" and len(args) <= 1:
                    target = self._resolve(args[0] if args else None)
                    if not target.is_dir():
                        return self._failure("not_a_directory", "target is not a directory")
                    self._cwd = target
                    return self._result(str(self._cwd), action="cd")

                if verb in {"ls", "dir"} and len(args) <= 1:
                    target = self._resolve(args[0] if args else None)
                    if _is_sensitive_path(target):
                        return self._failure("sensitive_file_blocked", "listing sensitive credential paths is blocked")
                    if not target.is_dir():
                        return self._failure("not_a_directory", "target is not a directory")
                    entries = []
                    truncated = False
                    scanned = 0
                    with os.scandir(target) as iterator:
                        for entry in iterator:
                            scanned += 1
                            if scanned > self.max_entries:
                                truncated = True
                                break
                            entry_path = target / entry.name
                            if _is_sensitive_path(entry_path):
                                continue
                            try:
                                info = entry.stat(follow_symlinks=False)
                                kind = "symlink" if stat.S_ISLNK(info.st_mode) else ("directory" if stat.S_ISDIR(info.st_mode) else "file")
                                entries.append({
                                    "name": entry.name,
                                    "type": kind,
                                    "size": info.st_size,
                                    "modified_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(info.st_mtime)),
                                })
                            except OSError:
                                continue
                    return self._result(
                        json.dumps(entries, ensure_ascii=False),
                        truncated=truncated,
                        entries=len(entries),
                    )

                if verb in {"cat", "type"} and len(args) == 1:
                    target = self._resolve(args[0])
                    if not target.is_file():
                        return self._failure("not_a_file", "target is not a regular file")
                    if _is_sensitive_path(target):
                        return self._failure("sensitive_file_blocked", "reading sensitive file names is blocked")
                    if target.suffix.casefold() not in _TEXT_SUFFIXES and target.name.casefold() not in _SPECIAL_TEXT_NAMES:
                        return self._failure("file_type_blocked", "file extension is not approved for text reading")
                    size = target.stat().st_size
                    if size > self.max_read_bytes:
                        return self._failure("file_too_large", "file exceeds the configured read limit")
                    raw = target.read_bytes()
                    if b"\x00" in raw:
                        return self._failure("binary_file_blocked", "binary files cannot be read through this tool")
                    # Structured credential stores and private-key material are refused.
                    # Ordinary text containing credential assignments is safe to inspect
                    # only after _redact_text removes the values from the returned output.
                    non_redactable_secret = re.compile(
                        rb"(?i)(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|\"auths\"\s*:|"
                        rb"client[-_]?key[-_]?data|certificate[-_]?authority[-_]?data|AGE-SECRET-KEY-)"
                    )
                    if non_redactable_secret.search(raw):
                        return self._failure("sensitive_file_blocked", "file content contains key material or a credential store")
                    try:
                        output = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        return self._failure("encoding_unsupported", "file is not valid UTF-8 text")
                    return self._result(_redact_text(output), bytes_read=len(raw))

                if verb == "git":
                    argv = self._git_argv(args)
                    boundaries = [root for root in self.allowed_roots if self._is_allowed(self._cwd) and self._cwd.is_relative_to(root)]
                    if not boundaries:
                        return self._failure("git_repository_outside_allowed_roots", "working directory has no allowed root")
                    boundary = max(boundaries, key=lambda root: len(root.parts))
                    try:
                        _repo_root, git_dir = _git_repository_within(boundary, self._cwd)
                    except PermissionError as exc:
                        return self._failure("git_repository_outside_allowed_roots", str(exc))
                    try:
                        _assert_trusted_git_config(git_dir)
                    except (OSError, UnicodeError, ValueError) as exc:
                        return self._failure("git_config_rejected", str(exc) or "repository Git config is not trusted")

                    safe_options = [
                        "-c", "core.fsmonitor=false",
                        "-c", "core.untrackedCache=false",
                        "-c", "core.pager=cat",
                        "-c", "log.showSignature=false",
                        "--no-pager",
                    ]
                    argv = ["git", *safe_options, *argv[1:]]
                    if args[0] in {"diff", "show"}:
                        subcommand_index = len(safe_options) + 1
                        argv[subcommand_index + 1:subcommand_index + 1] = ["--no-ext-diff", "--no-textconv"]
                    started = time.monotonic()
                    completed = subprocess.run(
                        argv,
                        cwd=str(self._cwd),
                        env={
                            key: os.environ[key]
                            for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
                            if key in os.environ
                        } | {
                            "GIT_CONFIG_NOSYSTEM": "1",
                            "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_OPTIONAL_LOCKS": "0",
                            "GIT_TERMINAL_PROMPT": "0",
                            "GIT_PAGER": "cat",
                            "PAGER": "cat",
                            "GIT_CEILING_DIRECTORIES": str(boundary),
                        },
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout_seconds,
                        shell=False,
                        check=False,
                    )
                    raw_output = completed.stdout or ""
                    if args[:2] == ["remote", "-v"]:
                        raw_output = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", raw_output)
                        raw_output = re.sub(r"(?i)(token|key|password)=([^&\s]+)", r"\1=[REDACTED]", raw_output)
                    output = _redact_text(raw_output)[:MAX_OUTPUT_CHARS]
                    error = _redact_text(completed.stderr or "")[:4_000]
                    return {
                        "success": completed.returncode == 0,
                        "status": "completed" if completed.returncode == 0 else "command_failed",
                        "command": "git",
                        "cwd": str(self._cwd),
                        "output": output,
                        "error": error,
                        "exit_code": completed.returncode,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "truncated": len(completed.stdout or "") > MAX_OUTPUT_CHARS,
                    }

                return self._failure("command_rejected", "command is not in the navigation allowlist")
        except PermissionError as exc:
            return self._failure("path_outside_allowed_roots", str(exc))
        except FileNotFoundError:
            return self._failure("path_not_found", "path does not exist")
        except NotADirectoryError:
            return self._failure("not_a_directory", "a path component is not a directory")
        except ValueError as exc:
            return self._failure("command_rejected", str(exc))
        except subprocess.TimeoutExpired:
            return self._failure("timeout", "Git command exceeded its timeout")
        except OSError as exc:
            logger.warning("Shell navigation failed: %s", type(exc).__name__)
            return self._failure("operation_failed", type(exc).__name__)

    @staticmethod
    def _result(output: str, **metadata: Any) -> dict[str, Any]:
        return {
            "success": True,
            "status": "completed",
            "output": output[:MAX_OUTPUT_CHARS],
            "truncated": len(output) > MAX_OUTPUT_CHARS,
            **metadata,
        }

    @staticmethod
    def _failure(status: str, message: str) -> dict[str, Any]:
        return {"success": False, "status": status, "output": "", "error": message}


_default_navigator: ShellNavigator | None = None
_default_lock = threading.Lock()


def shell_navigate(command: str, *, timeout_seconds: int = 10) -> dict[str, Any]:
    """Use the process-local, stateful shell navigation session."""
    global _default_navigator
    with _default_lock:
        if _default_navigator is None:
            _default_navigator = ShellNavigator()
        navigator = _default_navigator
    return navigator.execute(command, timeout_seconds=timeout_seconds)
