"""Host abstraction contract regression tests."""
from datetime import UTC, datetime

import pytest
from app.domain.ports.host_port import (
    DiskUsage,
    HostIdentity,
    HostPort,
    ProcessInfo,
    ResourceSnapshot,
)


class FakeHost(HostPort):
    def get_identity(self):
        return HostIdentity("test-host", "Linux", "6.x", "x86_64", "3.12")

    def get_resources(self):
        return ResourceSnapshot(
            captured_at=datetime.now(UTC),
            cpu_percent=12.5,
            memory_total_bytes=1000,
            memory_available_bytes=400,
            memory_used_bytes=600,
            memory_percent=60.0,
            disks=(DiskUsage("/", 2000, 1000, 1000, 50.0),),
        )

    def list_processes(self, limit=50):
        limit = self.validate_process_limit(limit)
        return tuple(
            ProcessInfo(pid=i, name=f"proc-{i}", status="running",
                        cpu_percent=float(i), memory_rss_bytes=i * 1024)
            for i in range(min(limit, 3), 0, -1)
        )


def test_host_contract_is_platform_neutral():
    host = FakeHost()
    assert host.get_identity().operating_system == "Linux"
    assert host.get_resources().memory_percent == 60.0
    assert host.list_processes(2)[0].pid == 2


@pytest.mark.parametrize("limit", [0, 501, -1])
def test_process_limit_rejects_out_of_range_values(limit):
    with pytest.raises(ValueError):
        HostPort.validate_process_limit(limit)


@pytest.mark.parametrize("limit", [True, 1.5, "10", None])
def test_process_limit_rejects_non_integer_values(limit):
    with pytest.raises(TypeError):
        HostPort.validate_process_limit(limit)


def test_snapshot_is_immutable():
    snapshot = FakeHost().get_resources()
    with pytest.raises((AttributeError, TypeError)):
        snapshot.cpu_percent = 99.0


def test_host_adapter_dependency_is_optional_and_explicit():
    from app.adapters.edge.host.psutil_host_adapter import PsutilHostAdapter

    try:
        adapter = PsutilHostAdapter()
    except RuntimeError as exc:
        assert "requirements/host.txt" in str(exc)
    else:
        assert adapter.get_identity().hostname
        assert adapter.get_resources().memory_total_bytes > 0
        assert len(adapter.list_processes(limit=5)) <= 5
