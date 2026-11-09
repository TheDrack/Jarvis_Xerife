"""Tests for the bounded, metadata-only host storage inventory."""
from __future__ import annotations

import pytest

from app.adapters.edge.host_storage_diagnostics import (
    _scan_root,
    collect_host_storage_diagnostics,
)


def test_scan_reports_directory_and_file_sizes_without_reading_contents(tmp_path):
    cache = tmp_path / "Users" / "Example" / ".cache"
    cache.mkdir(parents=True)
    large_file = cache / "model.bin"
    large_file.write_bytes(b"x" * 4096)
    log_file = cache / "worker.log"
    log_file.write_bytes(b"y" * 1024)

    result = _scan_root(tmp_path)

    assert result["success"] is True
    assert result["read_only"] is True
    assert result["scan"]["scanned_files"] == 2
    assert result["largest_files"][0]["path"] == str(large_file)
    assert result["largest_files"][0]["size_bytes"] == 4096
    sizes = {item["path"]: item["size_bytes"] for item in result["largest_directories"]}
    assert sizes[str(cache)] == 5120
    assert sizes[str(cache.parent)] == 5120
    assert any(item["path"] == str(cache) for item in result["temporary_cache_log_directories"])
    assert result["privacy"]["file_contents_read"] is False


def test_scan_stops_after_maximum_visited_entries(tmp_path):
    for index in range(120):
        (tmp_path / f"file-{index:03}.bin").write_bytes(b"x")

    result = _scan_root(tmp_path, max_entries=100)

    assert result["scan"]["visited_entries"] == 100
    assert result["scan"]["truncated"] is True
    assert result["scan"]["stopped_reason"] == "entry_limit"


def test_scan_skips_symlinks_and_does_not_follow_them(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    secret = outside / "must-not-be-inventoried.bin"
    secret.write_bytes(b"secret")
    link = tmp_path / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this host")

    result = _scan_root(tmp_path)

    assert result["scan"]["scanned_files"] == 0
    assert all("must-not-be-inventoried" not in item["path"] for item in result["largest_files"])
    assert result["privacy"]["symlinks_followed"] is False


def test_scan_respects_depth_limit(tmp_path):
    level_one = tmp_path / "one"
    level_two = level_one / "two"
    level_three = level_two / "three"
    level_three.mkdir(parents=True)
    (level_one / "visible.bin").write_bytes(b"123")
    (level_two / "visible-too.bin").write_bytes(b"1234")
    (level_three / "beyond-depth.bin").write_bytes(b"12345")

    result = _scan_root(tmp_path, max_depth=1)

    paths = {item["path"] for item in result["largest_files"]}
    assert str(level_one / "visible.bin") in paths
    assert str(level_two / "visible-too.bin") not in paths
    assert str(level_three / "beyond-depth.bin") not in paths


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_depth": 0}, "max_depth"),
        ({"max_depth": 7}, "max_depth"),
        ({"max_entries": 99}, "max_entries"),
        ({"max_entries": 50_001}, "max_entries"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": 16}, "timeout_seconds"),
    ],
)
def test_scan_rejects_out_of_bounds_limits(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        _scan_root(tmp_path, **kwargs)


def test_collect_uses_only_the_system_drive(monkeypatch):
    monkeypatch.setenv("SystemDrive", "not-a-drive")

    result = collect_host_storage_diagnostics()

    assert result == {
        "success": False,
        "status": "invalid_system_drive",
        "read_only": True,
    }
