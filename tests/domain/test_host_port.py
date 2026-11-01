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


def test_host_adapter_dependency_is_optional_and_explicit(monkeypatch):
    import builtins

    from app.adapters.edge.host.psutil_host_adapter import PsutilHostAdapter

    original_import = builtins.__import__

    def import_without_psutil(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "psutil":
            raise ImportError("psutil intentionally unavailable in this test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_psutil)
    with pytest.raises(RuntimeError, match="requirements/host.txt"):
        PsutilHostAdapter()


def test_psutil_adapter_normalizes_linux_host_without_os_specific_calls(monkeypatch):
    from types import SimpleNamespace

    import app.adapters.edge.host.psutil_host_adapter as adapter_module
    from app.adapters.edge.host.psutil_host_adapter import PsutilHostAdapter

    class FakeProcess:
        def __init__(self):
            self.info = {
                "pid": 42,
                "name": "systemd",
                "status": "running",
                "memory_info": SimpleNamespace(rss=4096),
                "create_time": 1234.5,
            }

        def cpu_percent(self, interval=None):
            return 3.25

    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        class ZombieProcess(Exception):
            pass

        @staticmethod
        def virtual_memory():
            return SimpleNamespace(
                total=8192, available=4096, used=4096, percent=50.0
            )

        @staticmethod
        def disk_partitions(all=False):
            return [SimpleNamespace(mountpoint="/")]

        @staticmethod
        def disk_usage(mountpoint):
            assert mountpoint == "/"
            return SimpleNamespace(total=16384, used=8192, free=8192, percent=50.0)

        @staticmethod
        def cpu_percent(interval=0.1):
            return 7.5

        @staticmethod
        def process_iter(attrs):
            assert attrs == ["pid", "name", "status", "memory_info", "create_time"]
            return [FakeProcess()]

    monkeypatch.setattr(adapter_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(adapter_module.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(adapter_module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(adapter_module.platform, "python_version", lambda: "3.12.10")
    monkeypatch.setattr(adapter_module.socket, "gethostname", lambda: "ubuntu-vm")

    adapter = PsutilHostAdapter(psutil_module=FakePsutil)
    identity = adapter.get_identity()
    resources = adapter.get_resources()
    processes = adapter.list_processes(limit=10)

    assert identity.hostname == "ubuntu-vm"
    assert identity.operating_system == "Linux"
    assert identity.architecture == "x86_64"
    assert resources.cpu_percent == 7.5
    assert resources.memory_percent == 50.0
    assert resources.disks[0].mountpoint == "/"
    assert processes == (
        ProcessInfo(
            pid=42,
            name="systemd",
            status="running",
            cpu_percent=3.25,
            memory_rss_bytes=4096,
            created_at_epoch=1234.5,
        ),
    )


def test_psutil_adapter_selects_stable_top_n_from_a_lazy_process_iterator(monkeypatch):
    from types import SimpleNamespace

    import app.adapters.edge.host.psutil_host_adapter as adapter_module
    from app.adapters.edge.host.psutil_host_adapter import PsutilHostAdapter

    records = [
        (1, 10.0, 1000),
        (2, 20.0, 50),
        (3, 20.0, 80),
        (4, 20.0, 80),
        (5, 5.0, 5000),
    ]

    class FakeProcess:
        def __init__(self, pid, cpu, rss):
            self.info = {
                "pid": pid,
                "name": f"process-{pid}",
                "status": "running",
                "memory_info": SimpleNamespace(rss=rss),
                "create_time": float(pid),
            }
            self._cpu = cpu

        def cpu_percent(self, interval=None):
            return self._cpu

    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        class ZombieProcess(Exception):
            pass

        @staticmethod
        def process_iter(attrs):
            assert attrs == ["pid", "name", "status", "memory_info", "create_time"]
            return (
                FakeProcess(pid, cpu, rss)
                for pid, cpu, rss in records
            )

    original_nlargest = adapter_module.heapq.nlargest

    def assert_lazy_top_n(n, iterable, key=None):
        assert n == 3
        assert iter(iterable) is iterable
        assert not isinstance(iterable, (list, tuple))
        return original_nlargest(n, iterable, key=key)

    monkeypatch.setattr(adapter_module.heapq, "nlargest", assert_lazy_top_n)

    processes = PsutilHostAdapter(psutil_module=FakePsutil).list_processes(limit=3)

    assert [process.pid for process in processes] == [3, 4, 2]
    assert len(processes) == 3
