"""Canonical path policy for repository mutations performed by autonomous code.

This module is deliberately kept under the protected application/security tree.
It prevents lexical traversal and checks resolved paths so existing symlinks
cannot redirect writes outside the checkout or into protected code.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional


PROTECTED_PATH_PREFIXES = (
    "app/core",
    "capabilities",
    "app/domain/capabilities",
    "app/adapters/infrastructure",
    "app/application/security",
)
FROZEN_DIRECTORY = ".frozen"
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UnsafeRepositoryPath(ValueError):
    """Raised when a proposed repository path is ambiguous or escapes policy."""


def normalize_relative_path(raw_path: str) -> str:
    """Normalize a repository-relative path and reject traversal/OS aliases."""
    if not isinstance(raw_path, str):
        raise UnsafeRepositoryPath("path must be a string")

    raw = raw_path
    if not raw or raw != raw.strip() or "\x00" in raw:
        raise UnsafeRepositoryPath("path must be non-empty, trimmed, and contain no NUL")

    windows_path = PureWindowsPath(raw)
    if windows_path.is_absolute() or windows_path.drive:
        raise UnsafeRepositoryPath("absolute paths and Windows drive paths are forbidden")

    normalized = raw.replace("\\", "/")
    if normalized.startswith("/"):
        raise UnsafeRepositoryPath("absolute paths are forbidden")

    parts = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafeRepositoryPath("parent traversal is forbidden")
        if ":" in part or part.endswith((" ", ".")):
            raise UnsafeRepositoryPath("Windows path aliases and alternate streams are forbidden")
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise UnsafeRepositoryPath("Windows reserved device names are forbidden")
        parts.append(part)

    if not parts:
        raise UnsafeRepositoryPath("path resolves to an empty repository path")

    return PurePosixPath(*parts).as_posix()


def validate_filename(name: str) -> str:
    """Validate a single file stem; directory separators are never accepted."""
    if not isinstance(name, str) or "/" in name or "\\" in name:
        raise UnsafeRepositoryPath("filename must be a single path component")
    return normalize_relative_path(name)


def resolve_repository_path(
    repository_root: Path,
    relative_path: str,
    *,
    reject_symlinks: bool = False,
) -> tuple[Path, str, str]:
    """Resolve a path and prove it remains inside the resolved repository root.

    Existing symlink components are resolved strictly before the final containment
    check; dangling links and loops fail closed. When reject_symlinks is true, any
    symlink component is rejected (used by direct filesystem writes).

    Returns (absolute_resolved_path, normalized_lexical_path, resolved_relative_path).
    """
    normalized = normalize_relative_path(relative_path)
    root = Path(repository_root).resolve()
    parts = PurePosixPath(normalized).parts

    current = root
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                if reject_symlinks:
                    raise UnsafeRepositoryPath("symlink components are forbidden for writes")
                try:
                    current.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise UnsafeRepositoryPath("symlink component cannot be resolved") from exc
        except OSError as exc:
            raise UnsafeRepositoryPath("unable to inspect path component") from exc

    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=False)
        resolved_relative = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise UnsafeRepositoryPath("path escapes the repository or cannot be resolved") from exc

    return resolved, normalized, resolved_relative


def protected_prefix_for(relative_path: str) -> Optional[str]:
    """Return the protected prefix containing a repository-relative path."""
    normalized = relative_path.replace("\\", "/").strip("/").casefold()
    for prefix in PROTECTED_PATH_PREFIXES:
        candidate = prefix.casefold()
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return prefix
    return None


def contains_frozen_directory(relative_path: str) -> bool:
    """Return whether .frozen appears as a complete path segment."""
    return FROZEN_DIRECTORY.casefold() in {
        part.casefold() for part in relative_path.replace("\\", "/").split("/")
    }
