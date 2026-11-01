"""Optional psutil-backed host adapter for Windows and Linux.

Install the optional dependency from requirements/host.txt. This module is
intentionally imported only by the opt-in Host profile.
"""
from __future__ import annotations

import heapq
import platform
import socket
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from app.domain.ports.host_port import (
    DiskUsage,
    HostIdentity,
    HostPort,
    ProcessInfo,
    ResourceSnapshot,
)


class PsutilHostAdapter(HostPort):
    """Cross-platform, read-only host telemetry adapter."""

    def __init__(self, psutil_module=None) -> None:
        if psutil_module is None:
            try:
                import psutil as psutil_module
            except ImportError as exc:
                raise RuntimeError(
                    "Host telemetry requires the optional psutil dependency; "
                    "install requirements/host.txt"
                ) from exc
        self._psutil = psutil_module

    def get_identity(self) -> HostIdentity:
        return HostIdentity(
            hostname=socket.gethostname(),
            operating_system=platform.system(),
            os_release=platform.release(),
            architecture=platform.machine(),
            python_version=platform.python_version(),
        )

    def get_resources(self) -> ResourceSnapshot:
        psutil = self._psutil
        memory = psutil.virtual_memory()
        disks: list[DiskUsage] = []
        seen: set[str] = set()

        for partition in psutil.disk_partitions(all=False):
            mountpoint = partition.mountpoint
            if mountpoint in seen:
                continue
            seen.add(mountpoint)
            try:
                usage = psutil.disk_usage(mountpoint)
            except (OSError, PermissionError):
                continue
            disks.append(
                DiskUsage(
                    mountpoint=mountpoint,
                    total_bytes=int(usage.total),
                    used_bytes=int(usage.used),
                    free_bytes=int(usage.free),
                    percent=float(usage.percent),
                )
            )

        return ResourceSnapshot(
            captured_at=datetime.now(UTC),
            cpu_percent=float(psutil.cpu_percent(interval=0.1)),
            memory_total_bytes=int(memory.total),
            memory_available_bytes=int(memory.available),
            memory_used_bytes=int(memory.used),
            memory_percent=float(memory.percent),
            disks=tuple(disks),
        )

    def _iter_process_info(self) -> Iterator[ProcessInfo]:
        """Yield readable process snapshots without retaining the full process table."""
        for process in self._psutil.process_iter(
            attrs=["pid", "name", "status", "memory_info", "create_time"]
        ):
            try:
                info = process.info
                yield ProcessInfo(
                    pid=int(info["pid"]),
                    name=str(info.get("name") or "unknown"),
                    status=str(info.get("status") or "unknown"),
                    cpu_percent=float(process.cpu_percent(interval=None)),
                    memory_rss_bytes=int(
                        getattr(info.get("memory_info"), "rss", 0) or 0
                    ),
                    created_at_epoch=(
                        float(info["create_time"])
                        if info.get("create_time") is not None
                        else None
                    ),
                )
            except (
                self._psutil.NoSuchProcess,
                self._psutil.AccessDenied,
                self._psutil.ZombieProcess,
            ):
                continue

    def list_processes(self, limit: int = 50) -> Sequence[ProcessInfo]:
        """Return top-N processes using O(limit) intermediate memory.

        The process table still has to be traversed to identify the true top-N,
        but the adapter no longer builds and sorts a list containing every
        process on the host.
        """
        limit = self.validate_process_limit(limit)
        ranked = heapq.nlargest(
            limit,
            enumerate(self._iter_process_info()),
            key=lambda entry: (
                entry[1].cpu_percent,
                entry[1].memory_rss_bytes,
                -entry[0],
            ),
        )
        return tuple(process for _, process in ranked)
