import asyncio
import ipaddress

import pytest

from scripts.network_inventory import lan_inventory
from scripts.network_inventory.lan_inventory import (
    parse_arp_addresses,
    redact_server_header,
    validate_network,
)


@pytest.mark.parametrize(("cidr", "expected"), [
    ("10.0.0.0/24", "10.0.0.0/24"),
    ("172.16.4.0/24", "172.16.4.0/24"),
    ("192.168.1.0/24", "192.168.1.0/24"),
    ("10.0.0.0/22", "10.0.0.0/22"),
])
def test_accepts_bounded_rfc1918_networks(cidr, expected):
    assert str(validate_network(cidr)) == expected


@pytest.mark.parametrize("cidr", [
    "8.8.8.0/24", "100.64.0.0/24", "169.254.1.0/24",
    "127.0.0.0/24", "192.168.0.0/16", "2001:db8::/64", "not-a-network",
])
def test_rejects_non_rfc1918_or_oversized_networks(cidr):
    with pytest.raises(ValueError):
        validate_network(cidr)


def test_arp_parser_filters_addresses_to_selected_subnet():
    network = ipaddress.ip_network("10.0.0.0/24")
    content = (
        "Interface: 10.0.0.21 --- 0x7\n"
        "  10.0.0.1  aa-bb-cc-dd-ee-ff  dynamic\n"
        "  10.0.1.1  11-22-33-44-55-66  dynamic\n"
        "  999.0.0.1  11-22-33-44-55-66  dynamic\n"
    )
    assert parse_arp_addresses(content, network) == {"10.0.0.1"}


def test_server_header_redacts_serial_number():
    value = "HP Deskjet; Serial Number: ABC123; firmware 1.0"
    assert "ABC123" not in redact_server_header(value)
    assert "[redacted]" in redact_server_header(value)


def test_probe_profile_is_bounded():
    assert len(lan_inventory.PORTS) <= 16
    assert lan_inventory.MAX_ADDRESSES == 1024


class _FakePingProcess:
    def __init__(self, semaphore, *, finish_immediately=False):
        self.returncode = None
        self.kill_called = False
        self.reaped = False
        self.semaphore_held_during_reap = None
        self.wait_started = asyncio.Event()
        self._finished = asyncio.Event()
        self._semaphore = semaphore
        if finish_immediately:
            self._finished.set()

    async def wait(self):
        self.wait_started.set()
        await self._finished.wait()
        self.semaphore_held_during_reap = self._semaphore.locked()
        self.returncode = -9 if self.kill_called else 0
        self.reaped = True
        return self.returncode

    def kill(self):
        self.kill_called = True
        self._finished.set()


@pytest.mark.parametrize("cancel_task", [False, True], ids=["timeout", "cancellation"])
def test_ping_host_kills_and_reaps_child_before_releasing_semaphore(
    monkeypatch, cancel_task
):
    async def scenario():
        semaphore = asyncio.Semaphore(1)
        process = _FakePingProcess(semaphore)

        async def create_subprocess_exec(*args, **kwargs):
            return process

        monkeypatch.setattr(
            lan_inventory.asyncio,
            "create_subprocess_exec",
            create_subprocess_exec,
        )
        monkeypatch.setattr(lan_inventory, "PING_TIMEOUT", 0.01)

        task = asyncio.create_task(lan_inventory.ping_host("192.168.1.10", semaphore))
        await asyncio.wait_for(process.wait_started.wait(), timeout=1)

        if cancel_task:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await task is False

        assert process.kill_called
        assert process.reaped
        assert process.returncode == -9
        assert process.semaphore_held_during_reap is True
        assert semaphore.locked() is False

    asyncio.run(scenario())


def test_ping_host_does_not_kill_a_child_that_exited_normally(monkeypatch):
    async def scenario():
        semaphore = asyncio.Semaphore(1)
        process = _FakePingProcess(semaphore, finish_immediately=True)

        async def create_subprocess_exec(*args, **kwargs):
            return process

        monkeypatch.setattr(
            lan_inventory.asyncio,
            "create_subprocess_exec",
            create_subprocess_exec,
        )

        assert await lan_inventory.ping_host("192.168.1.10", semaphore) is True
        assert process.reaped
        assert process.returncode == 0
        assert process.kill_called is False
        assert semaphore.locked() is False

    asyncio.run(scenario())
