"""Read-only host resource diagnostics tests."""
from datetime import UTC, datetime

import pytest

from app.adapters.edge.host_resource_diagnostics import collect_host_resource_diagnostics
from app.domain.ports.host_port import (
    DiskUsage,
    HostIdentity,
    HostPort,
    ProcessInfo,
    ResourceSnapshot,
)


class FakeHost(HostPort):
    def get_identity(self):
        return HostIdentity("test-pc", "Windows", "11", "AMD64", "3.12")

    def get_resources(self):
        return ResourceSnapshot(
            captured_at=datetime(2026, 11, 8, tzinfo=UTC),
            cpu_percent=25.0,
            memory_total_bytes=16_000,
            memory_available_bytes=4_000,
            memory_used_bytes=12_000,
            memory_percent=75.0,
            disks=(DiskUsage("C:\\", 100_000, 90_000, 10_000, 90.0),),
        )

    def list_processes(self, limit=50):
        self.validate_process_limit(limit)
        return (
            ProcessInfo(10, "cpu-heavy.exe", "running", 95.0, 1024),
            ProcessInfo(11, "memory-heavy.exe", "running", 2.5, 8192),
        )

    def list_processes_by_memory(self, limit=50):
        self.validate_process_limit(limit)
        return (
            ProcessInfo(11, "memory-heavy.exe", "running", 2.5, 8192),
            ProcessInfo(10, "cpu-heavy.exe", "running", 95.0, 1024),
        )


def test_host_resource_diagnostics_returns_read_only_snapshot():
    result = collect_host_resource_diagnostics(FakeHost(), process_limit=10)

    assert result["success"] is True
    assert result["read_only"] is True
    assert result["identity"]["hostname"] == "test-pc"
    assert result["resources"]["memory_percent"] == 75.0
    assert result["resources"]["disks"][0]["free_bytes"] == 10_000
    assert result["top_cpu_processes"][0]["name"] == "cpu-heavy.exe"
    assert result["top_memory_processes"][0]["name"] == "memory-heavy.exe"
    assert result["privacy"]["command_lines_collected"] is False
    assert result["privacy"]["environment_variables_collected"] is False


@pytest.mark.parametrize("limit", [0, 51, -1, True, 1.5, "10", None])
def test_host_resource_diagnostics_rejects_invalid_process_limit(limit):
    with pytest.raises((TypeError, ValueError)):
        collect_host_resource_diagnostics(FakeHost(), process_limit=limit)
