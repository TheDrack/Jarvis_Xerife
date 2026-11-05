from __future__ import annotations

import httpx

from app.adapters.infrastructure.osint.wigle_adapter import WigleAdapter
from app.domain.intelligence.osint import Coordinate, Signal


def test_wigle_converts_radius_to_bbox_and_returns_wifi_signals() -> None:
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [
                    {
                        "ssid": "LabNet",
                        "netid": "AA:BB:CC:DD:EE:FF",
                        "trilat": -27.1,
                        "trilong": -48.9,
                        "encryption": "WPA2",
                        "qos": 6,
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WigleAdapter(
        client=client,
        username_provider=lambda: "test-user",
        token_provider=lambda: "test-token",
    )
    signals = adapter.query_radius(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        2,
        {"kind": "wifi", "limit": 20},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert isinstance(signal, Signal)
    assert signal.kind == "wifi"
    assert signal.identifier == "AA:BB:CC:DD:EE:FF"
    assert signal.geo is not None
    assert signal.metadata["ssid"] == "LabNet"
    assert requests_seen[0].url.path.endswith("/network/search")
    assert "latrange1" in requests_seen[0].url.params
    assert "latrange2" in requests_seen[0].url.params
    assert requests_seen[0].url.params["resultsPerPage"] == "20"


def test_wigle_can_capture_bluetooth_history_as_distinct_signals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/bluetooth/search")
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [
                    {
                        "name": "Beacon",
                        "mac": "11:22:33:44:55:66",
                        "trilat": -27.2,
                        "trilong": -48.8,
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WigleAdapter(
        client=client,
        username_provider=lambda: "test-user",
        token_provider=lambda: "test-token",
    )
    signals = adapter.query_radius(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        1,
        {"kind": "bluetooth"},
    )

    assert signals[0].kind == "bluetooth"
    assert signals[0].identifier == "11:22:33:44:55:66"


def test_wigle_rejects_unbounded_radius() -> None:
    adapter = WigleAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
        username_provider=lambda: "test-user",
        token_provider=lambda: "test-token",
    )
    try:
        adapter.query_radius(
            Coordinate(lat=0, lon=0, accuracy_m=1, source="gps"),
            101,
            {"kind": "wifi"},
        )
    except ValueError as exc:
        assert "100" in str(exc)
    else:
        raise AssertionError("WiGLE query radius must remain bounded")
