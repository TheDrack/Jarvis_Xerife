"""Bounded, read-only storage inventory for the local Windows host.

Only filesystem metadata is inspected. File contents are never opened.
"""
from __future__ import annotations

import os
import stat
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

_MAX_DEPTH = 4
_MAX_ENTRIES = 20_000
_MAX_SECONDS = 8.0
_MAX_RESULTS = 30
_REPARSE_POINT = 0x400
_PROTECTED_DIRS = frozenset(
    {
        "windows",
        "program files",
        "program files (x86)",
        "$recycle.bin",
        "system volume information",
        "recovery",
        "config.msi",
    }
)
_SPECIAL_DIR_MARKERS = ("temp", "tmp", "cache", "caches", "log", "logs")


def _is_reparse_point(metadata: os.stat_result) -> bool:
    """Return true for symlinks and Windows junctions/reparse points."""
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & _REPARSE_POINT)


def _scan_root(
    root: Path,
    *,
    max_depth: int = _MAX_DEPTH,
    max_entries: int = _MAX_ENTRIES,
    timeout_seconds: float = _MAX_SECONDS,
) -> dict[str, Any]:
    """Walk a bounded directory tree and aggregate file metadata only."""
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 6:
        raise ValueError("max_depth must be an integer between 1 and 6")
    if (
        isinstance(max_entries, bool)
        or not isinstance(max_entries, int)
        or not 100 <= max_entries <= 50_000
    ):
        raise ValueError("max_entries must be an integer between 100 and 50000")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("timeout_seconds must be numeric")
    if not 1 <= timeout_seconds <= 15:
        raise ValueError("timeout_seconds must be between 1 and 15 seconds")

    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("scan root must be a directory")

    started = time.monotonic()
    deadline = started + float(timeout_seconds)
    stack: list[tuple[Path, int, tuple[Path, ...]]] = [(root, 0, ())]
    directory_sizes: dict[Path, int] = defaultdict(int)
    directory_depths: dict[Path, int] = {}
    extension_sizes: dict[str, int] = defaultdict(int)
    extension_counts: dict[str, int] = defaultdict(int)
    largest_files: list[dict[str, Any]] = []
    visited_entries = 0
    scanned_directories = 0
    scanned_files = 0
    skipped_entries = 0
    stopped_reason: str | None = None

    while stack:
        if time.monotonic() >= deadline:
            stopped_reason = "time_limit"
            break
        directory, depth, ancestors = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = iterator
                for entry in entries:
                    if time.monotonic() >= deadline:
                        stopped_reason = "time_limit"
                        break
                    if visited_entries >= max_entries:
                        stopped_reason = "entry_limit"
                        break
                    visited_entries += 1
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except (OSError, PermissionError):
                        skipped_entries += 1
                        continue

                    if _is_reparse_point(metadata):
                        skipped_entries += 1
                        continue

                    path = Path(entry.path)
                    if stat.S_ISDIR(metadata.st_mode):
                        name = entry.name.casefold()
                        if name in _PROTECTED_DIRS or depth >= max_depth:
                            skipped_entries += 1
                            continue
                        scanned_directories += 1
                        directory_depths[path] = depth + 1
                        directory_sizes.setdefault(path, 0)
                        stack.append((path, depth + 1, (*ancestors, path)))
                    elif stat.S_ISREG(metadata.st_mode):
                        scanned_files += 1
                        size = max(0, int(metadata.st_size))
                        for parent in ancestors:
                            directory_sizes[parent] += size
                        suffix = path.suffix.casefold() or "[no extension]"
                        extension_sizes[suffix] += size
                        extension_counts[suffix] += 1
                        largest_files.append(
                            {"path": str(path), "size_bytes": size, "extension": suffix}
                        )
                    else:
                        skipped_entries += 1
                if stopped_reason:
                    break
        except (OSError, PermissionError):
            skipped_entries += 1

    largest_files.sort(key=lambda item: item["size_bytes"], reverse=True)
    largest_directories = [
        {"path": str(path), "size_bytes": size, "depth": directory_depths[path]}
        for path, size in directory_sizes.items()
    ]
    largest_directories.sort(key=lambda item: item["size_bytes"], reverse=True)

    special_directories = [
        item
        for item in largest_directories
        if any(
            marker in Path(item["path"]).name.casefold()
            for marker in _SPECIAL_DIR_MARKERS
        )
    ]
    extension_summary = [
        {
            "extension": extension,
            "file_count": count,
            "size_bytes": extension_sizes[extension],
        }
        for extension, count in extension_counts.items()
    ]
    extension_summary.sort(key=lambda item: item["size_bytes"], reverse=True)

    return {
        "success": True,
        "read_only": True,
        "root": str(root),
        "limits": {
            "max_depth": max_depth,
            "max_entries": max_entries,
            "timeout_seconds": float(timeout_seconds),
            "max_results": _MAX_RESULTS,
        },
        "scan": {
            "visited_entries": visited_entries,
            "scanned_directories": scanned_directories,
            "scanned_files": scanned_files,
            "skipped_entries": skipped_entries,
            "truncated": stopped_reason is not None,
            "stopped_reason": stopped_reason,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        },
        "largest_directories": largest_directories[:_MAX_RESULTS],
        "largest_files": largest_files[:_MAX_RESULTS],
        "temporary_cache_log_directories": special_directories[:_MAX_RESULTS],
        "largest_extensions": extension_summary[:_MAX_RESULTS],
        "privacy": {
            "file_contents_read": False,
            "file_contents_collected": False,
            "symlinks_followed": False,
            "junctions_followed": False,
        },
    }


def collect_host_storage_diagnostics() -> dict[str, Any]:
    """Inventory the system drive without accepting a caller-controlled path."""
    drive = os.environ.get("SystemDrive", "C:").strip()
    if len(drive) != 2 or drive[1:] != ":" or not drive[0].isalpha():
        return {
            "success": False,
            "status": "invalid_system_drive",
            "read_only": True,
        }
    root = Path(drive + os.sep)
    try:
        return _scan_root(root)
    except FileNotFoundError:
        return {
            "success": False,
            "status": "system_drive_unavailable",
            "read_only": True,
        }
    except PermissionError:
        return {
            "success": False,
            "status": "system_drive_access_denied",
            "read_only": True,
        }
    except (OSError, ValueError) as exc:
        return {
            "success": False,
            "status": "storage_diagnostic_failed",
            "error": type(exc).__name__,
            "read_only": True,
        }
