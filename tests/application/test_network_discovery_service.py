"""Tests for safe passive network discovery."""
from app.application.services.network_discovery_service import (
    _is_cloud_environment,
    _parse_linux_arp,
    _parse_windows_arp,
    discover_passive_neighbors,
)


def test_cloud_environment_is_not_misrepresented_as_user_lan():
    result = discover_passive_neighbors(environ={"RENDER": "true"}, platform="linux")
    assert result["available"] is False
    assert result["devices"] == []
    assert "cloud" in result["message"]


def test_linux_arp_parser_ignores_incomplete_and_invalid_entries():
    content = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.10     0x1        0x2         aa:bb:cc:dd:ee:ff     *        eth0
192.168.1.11     0x1        0x0         00:00:00:00:00:00     *        eth0
192.168.1.12     0x1        0x2         incomplete            *        eth0
8.8.8.8          0x1        0x2         aa:bb:cc:dd:ee:11     *        eth0
"""
    assert _parse_linux_arp(content) == [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:ff", "interface": "eth0"}
    ]


def test_windows_arp_parser_reads_interface_and_dynamic_neighbor():
    content = """Interface: 192.168.1.2 --- 0x9
  Internet Address      Physical Address      Type
  192.168.1.10          aa-bb-cc-dd-ee-ff     dynamic
  192.168.1.11          00-00-00-00-00-00     static
"""
    assert _parse_windows_arp(content) == [
        {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:ff", "interface": "192.168.1.2"}
    ]


def test_cloud_marker_detection_does_not_require_global_environment():
    assert _is_cloud_environment({"K_SERVICE": "jarvis"})
    assert not _is_cloud_environment({})
