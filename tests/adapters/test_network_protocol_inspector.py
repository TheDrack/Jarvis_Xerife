import ipaddress
from unittest.mock import patch, MagicMock

import pytest

from app.adapters.edge.network_protocol_inspector import (
    DEFAULT_PORTS,
    _normalize_ports,
    _private_ipv4,
    inspect_private_device,
)


def test_rejects_public_and_non_rfc1918_targets():
    for address in ("8.8.8.8", "127.0.0.1", "169.254.1.1", "100.64.0.1", "224.0.0.1", "2001:db8::1"):
        with pytest.raises(ValueError):
            _private_ipv4(address)


def test_accepts_only_rfc1918_private_ipv4_ranges():
    for address in ("10.1.2.3", "172.16.2.3", "172.31.255.254", "192.168.1.10"):
        assert str(_private_ipv4(address)) == address
    for address in ("172.32.0.1", "192.0.2.10", "198.18.0.1"):
        with pytest.raises(ValueError):
            _private_ipv4(address)


def test_port_list_is_bounded_and_validated():
    assert _normalize_ports(None) == list(DEFAULT_PORTS)
    assert _normalize_ports([80, 443, 80]) == [80, 443]
    with pytest.raises(ValueError):
        _normalize_ports([])
    with pytest.raises(ValueError):
        _normalize_ports(list(range(1, 34)))
    with pytest.raises(ValueError):
        _normalize_ports([0])
    with pytest.raises(ValueError):
        _normalize_ports([True])


def test_inspection_only_probes_selected_host_and_ports():
    with patch("app.adapters.edge.network_protocol_inspector._probe_tcp") as probe:
        probe.side_effect = lambda ip, port, timeout: (
            {"port": port, "transport": "tcp", "service": "http", "state": "open"}
            if port == 8080 else None
        )
        result = inspect_private_device("192.168.1.20", ports=[22, 8080], protocol_checks=False)
    assert result["success"] is True
    assert result["target"] == "192.168.1.20"
    assert result["ports_checked"] == [22, 8080]
    assert [item["port"] for item in result["open_ports"]] == [8080]
    assert result["protocols"] == {}
    assert result["active_probes_sent"] == 2
    assert probe.call_count == 2
    assert {call.args[0] for call in probe.call_args_list} == {"192.168.1.20"}


def test_protocol_checks_only_run_for_open_relevant_ports():
    with patch("app.adapters.edge.network_protocol_inspector._probe_tcp") as probe, \
         patch("app.adapters.edge.network_protocol_inspector._http_metadata") as http, \
         patch("app.adapters.edge.network_protocol_inspector._rtsp_options") as rtsp:
        probe.side_effect = lambda ip, port, timeout: (
            {"port": port, "transport": "tcp", "service": "x", "state": "open"}
            if port in {443, 554} else None
        )
        http.return_value = {"confirmed": True, "protocol": "https", "status": 401}
        rtsp.return_value = {"confirmed": True, "protocol": "rtsp", "status": 200}
        result = inspect_private_device("10.0.0.8", ports=[80, 443, 554], timeout=99)
    assert result["protocols"]["https"]["status"] == 401
    assert result["protocols"]["rtsp_554"]["status"] == 200
    assert "http" not in result["protocols"]
    assert http.call_args.kwargs["timeout"] == 3.0
    assert rtsp.call_count == 1


def test_public_target_is_rejected_before_any_network_probe():
    with patch("app.adapters.edge.network_protocol_inspector._probe_tcp") as probe:
        with pytest.raises(ValueError):
            inspect_private_device("1.1.1.1")
    probe.assert_not_called()
