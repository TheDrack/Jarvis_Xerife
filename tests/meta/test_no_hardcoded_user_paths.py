"""Guards the repository against machine-specific home paths.

Scripts must resolve locations through environment variables or
``machine.paths.json`` (see ``scripts/jarvis-machine.ps1``); documentation must
use placeholders. A literal home directory ties the repo to one computer and
breaks every other clone, including CI.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRECTORIES = {
    ".git", ".venv", "node_modules", "data", ".backups", "htmlcov",
    ".pytest_cache", ".tmp", "__pycache__", ".mypy_cache", ".ruff_cache",
    # Local harness copies generated from skills/; never committed.
    ".agents",
}
SKIP_RELATIVE_DIRECTORIES = {Path(".github") / "metabolism_logs"}
SKIP_FILES = {Path("report_final.json"), Path("tests/meta/test_no_hardcoded_user_paths.py")}
TEXT_SUFFIXES = {
    ".py", ".ps1", ".psm1", ".md", ".toml", ".yaml", ".yml", ".json",
    ".cmd", ".bat", ".sh", ".txt", ".service", ".ini", ".cfg",
}

# C:\Users\<name> / C:/Users/<name> and /Users/<name>, ignoring placeholders such
# as C:\Users\<usuario>, %USERPROFILE%\..., or $env:USERPROFILE.
WINDOWS_HOME = re.compile(r"[A-Za-z]:[\\/]Users[\\/]([^\\/\s`\"'<>]*)", re.IGNORECASE)
UNIX_HOME = re.compile(r"/Users/([^/\s`\"'<>]*)")


def _is_placeholder(segment: str) -> bool:
    if not segment:
        return True
    return segment.startswith(("<", "%", "$", "{"))


def _tracked_text_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(REPO_ROOT)
        if relative in SKIP_FILES:
            continue
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if any(relative.is_relative_to(skip) for skip in SKIP_RELATIVE_DIRECTORIES):
            continue
        files.append(path)
    return files


def test_no_literal_user_home_in_repository_files():
    offenders = []
    for path in _tracked_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in (WINDOWS_HOME, UNIX_HOME):
            for match in pattern.finditer(text):
                if not _is_placeholder(match.group(1)):
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")

    assert not offenders, (
        "Caminhos de usuário fixos encontrados. Use variável de ambiente, "
        "machine.paths.json ou placeholder:\n" + "\n".join(offenders)
    )


def test_machine_resolver_exposes_overrides():
    resolver = (REPO_ROOT / "scripts" / "jarvis-machine.ps1").read_text(encoding="utf-8")

    for variable in (
        "JARVIS_USER_HOME",
        "JARVIS_REPO_ROOT",
        "JARVIS_INSTALL_DIR",
        "JARVIS_NODE_ROOT",
    ):
        assert variable in resolver, f"{variable} precisa ser lida pelo resolver"
