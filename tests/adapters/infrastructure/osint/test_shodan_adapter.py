from __future__ import annotations

import httpx

from app.adapters.infrastructure.osint.shodan_adapter import ShodanAdapter
from app.domain.intelligence.osint import Coordinate


def test_shodan_queries_geo_radius_and_l1_cidr_then_normalizes_hosts() -> None:
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "ip_str": "203.0.113.8",
                        "port": 443,
                        "org": "Example ISP",
                        "location": {
                            "latitude": -27.1,
                            "longitude": -48.9,
                            "country_code": "BR",
                        },
                    },
                    {
                        "ip_str": "203.0.113.8",
                        "port": 8443,
                        "org": "Example ISP",
                        "location": {
                            "latitude": -27.1,
                            "longitude": -48.9,
                            "country_code": "BR",
                        },
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ShodanAdapter(client=client, api_key_provider=lambda: "test-key")
    hosts = adapter.query_radius(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        {"cidrs": ["203.0.113.0/24"], "limit": 20},
    )

    assert len(hosts) == 1
    assert hosts[0].ip == "203.0.113.8"
    assert hosts[0].ports == (443, 8443)
    assert hosts[0].geo_confidence == 0.6
    query = requests_seen[0].url.params["query"]
    assert "geo:-27.1,-48.9,5" in query
    assert "net:203.0.113.0/24" in query
    assert requests_seen[0].url.params["key"] == "test-key"


def test_shodan_requires_l1_network_ranges() -> None:
    adapter = ShodanAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
        api_key_provider=lambda: "test-key",
    )

    try:
        adapter.query_radius(
            Coordinate(lat=0, lon=0, accuracy_m=1, source="gps"),
            1,
            {},
        )
    except ValueError as exc:
        assert "CIDR" in str(exc)
    else:
        raise AssertionError("Shodan must require L1 network ranges")
