"""Portable host contracts.

The portable Harness depends on these abstractions, never on OS-specific APIs.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HostIdentity:
    hostname: str
    operating_system: str
    os_release: str
    architecture: str
    python_version: str


@dataclass(frozen=True, slots=True)
class DiskUsage:
    mountpoint: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    captured_at: datetime
    cpu_percent: float
    memory_total_bytes: int
    memory_available_bytes: int
    memory_used_bytes: int
    memory_percent: float
    disks: tuple[DiskUsage, ...]


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_rss_bytes: int
    created_at_epoch: float | None = None


class HostPort(ABC):
    """Read-only, provider-neutral contract for observing a host machine."""

    @abstractmethod
    def get_identity(self) -> HostIdentity:
        """Return stable host identity and platform metadata."""

    @abstractmethod
    def get_resources(self) -> ResourceSnapshot:
        """Return a point-in-time resource snapshot."""

    @abstractmethod
    def list_processes(self, limit: int = 50) -> Sequence[ProcessInfo]:
        """Return a bounded process inventory; never expose command lines or secrets."""

    @staticmethod
    def validate_process_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return limit
