from __future__ import annotations

import httpx

from app.adapters.infrastructure.osint.ipinfo_adapter import IPInfoAdapter


def _client(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "ipinfo.io"
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ipinfo_locate_returns_coordinate_and_conservative_confidence() -> None:
    client = _client(
        {
            "ip": "203.0.113.9",
            "loc": "-27.1,-48.9",
            "country": "BR",
            "asn": {
                "asn": "AS64500",
                "name": "Example ISP",
                "route": "203.0.113.0/24",
                "type": "isp",
            },
        }
    )
    result = IPInfoAdapter(client=client).locate("203.0.113.9")

    assert result.coordinate is not None
    assert result.coordinate.lat == -27.1
    assert result.coordinate.lon == -48.9
    assert result.geo_confidence == 0.35
    assert result.connection_type == "isp"


def test_ipinfo_reduces_geo_confidence_for_mobile_and_proxy() -> None:
    client = _client(
        {
            "ip": "203.0.113.9",
            "loc": "-27.1,-48.9",
            "country": "BR",
            "carrier": {"name": "Mobile Carrier"},
            "privacy": {"proxy": True},
        }
    )
    result = IPInfoAdapter(client=client).locate("203.0.113.9")

    assert result.connection_type == "mobile"
    assert result.is_proxy is True
    assert result.geo_confidence == 0.05


def test_ipinfo_resolve_extracts_asn_and_network_range() -> None:
    client = _client(
        {
            "ip": "203.0.113.9",
            "country": "BR",
            "asn": {
                "asn": "AS64500",
                "name": "Example ISP",
                "route": "203.0.113.0/24",
            },
        }
    )
    result = IPInfoAdapter(client=client).resolve("203.0.113.9")

    assert result.cidr == "203.0.113.0/24"
    assert result.asn == 64500
    assert result.org == "Example ISP"
    assert result.country == "BR"
