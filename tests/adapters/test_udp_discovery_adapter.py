from unittest.mock import patch, MagicMock

import pytest

from app.adapters.edge.udp_discovery_adapter import (
    _parse_onvif,
    _parse_ssdp,
    _timeout,
    discover_camera_protocols,
    discover_onvif,
    discover_ssdp,
)


def test_timeout_is_bounded():
    assert _timeout(2) == 2.0
    for value in (0, 0.1, 5.1, "invalid"):
        with pytest.raises(ValueError):
            _timeout(value)


def test_ssdp_parser_extracts_bounded_device_metadata():
    payload = (
        b"HTTP/1.1 200 OK\r\nSERVER: Test-UPnP/1.0\r\n"
        b"ST: urn:schemas-upnp-org:device:MediaServer:1\r\n"
        b"USN: uuid:test::upnp:rootdevice\r\n"
        b"LOCATION: http://192.168.1.2:80/device.xml\r\n\r\n"
    )
    result = _parse_ssdp(payload, "192.168.1.2")
    assert result["protocol"] == "ssdp"
    assert result["source_ip"] == "192.168.1.2"
    assert result["location"] == "http://192.168.1.2:80/device.xml"
    assert _parse_ssdp(b"garbage", "192.168.1.2") is None


def test_onvif_parser_extracts_xaddr_types_and_endpoint():
    payload = b'''<e:Envelope xmlns:e="urn:soap" xmlns:d="urn:discovery" xmlns:a="urn:addressing">
      <e:Body><d:ProbeMatches><d:ProbeMatch><a:EndpointReference><a:Address>urn:uuid:camera-1</a:Address></a:EndpointReference>
      <d:Types>dn:NetworkVideoTransmitter</d:Types><d:Scopes>onvif://www.onvif.org/name/Camera</d:Scopes>
      <d:XAddrs>http://192.168.1.20/onvif/device_service</d:XAddrs></d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>'''
    result = _parse_onvif(payload, "192.168.1.20")
    assert result["source_ip"] == "192.168.1.20"
    assert result["xaddrs"] == ["http://192.168.1.20/onvif/device_service"]
    assert result["types"] == ["dn:NetworkVideoTransmitter"]
    assert result["endpoint_reference"] == ["urn:uuid:camera-1"]


def test_onvif_parser_rejects_dtd_and_malformed_xml():
    assert _parse_onvif(b'<!DOCTYPE foo [<!ENTITY x "y">]><foo>&x;</foo>', "192.168.1.1") is None
    assert _parse_onvif(b"<broken", "192.168.1.1") is None


def test_ssdp_probe_uses_only_multicast_and_closes_socket():
    sock = MagicMock()
    sock.recvfrom.side_effect = [
        (b"HTTP/1.1 200 OK\r\nST: ssdp:all\r\nLOCATION: http://192.168.1.4/device.xml\r\n\r\n", ("192.168.1.4", 1900)),
        TimeoutError(),
    ]
    with patch("app.adapters.edge.udp_discovery_adapter.socket.socket", return_value=sock), \
         patch("app.adapters.edge.udp_discovery_adapter.time.monotonic", side_effect=[0, 0, 0, 3]):
        result = discover_ssdp(timeout=1)
    assert result["count"] == 1
    assert result["devices"][0]["source_ip"] == "192.168.1.4"
    sock.sendto.assert_called_once()
    assert sock.sendto.call_args.args[1] == ("239.255.255.250", 1900)
    sock.close.assert_called_once()


def test_camera_discovery_reports_ssdp_and_onvif_independently():
    with patch("app.adapters.edge.udp_discovery_adapter.discover_ssdp", return_value={"success": True, "devices": [], "count": 0}), \
         patch("app.adapters.edge.udp_discovery_adapter.discover_onvif", side_effect=OSError("no route")):
        result = discover_camera_protocols(timeout=1)
    assert result["success"] is False
    assert result["ssdp"]["success"] is True
    assert result["onvif"]["success"] is False
    assert result["errors"] == {"onvif": "OSError"}
