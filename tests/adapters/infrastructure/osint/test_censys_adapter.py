from __future__ import annotations

import httpx

from app.adapters.infrastructure.osint.censys_adapter import CensysAdapter
from app.domain.intelligence.osint import Coordinate


def test_censys_queries_geo_radius_and_l1_network_ranges() -> None:
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(
            200,
            json={
                "result": {
                    "hits": [
                        {
                            "host": {
                                "ip": "203.0.113.8",
                                "location": {
                                    "coordinates": {
                                        "latitude": -27.1,
                                        "longitude": -48.9,
                                    }
                                },
                                "services": [{"port": 443, "protocol": "HTTP"}],
                            }
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = CensysAdapter(client=client, token_provider=lambda: "test-token")
    hosts = adapter.query_radius(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        {"cidrs": ["203.0.113.0/24"], "limit": 25},
    )

    assert len(hosts) == 1
    assert hosts[0].ip == "203.0.113.8"
    assert hosts[0].ports == (443,)
    request = requests_seen[0]
    assert request.headers["Authorization"] == "Bearer test-token"
    query = request.read().decode()
    assert "geo_distance(host.location.coordinates,-27.1,-48.9,5km)" in query
    assert "203.0.113.0" in query


def test_censys_refuses_geospatial_query_without_l1_range() -> None:
    adapter = CensysAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
        token_provider=lambda: "test-token",
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
        raise AssertionError("Censys must require L1 network ranges")
