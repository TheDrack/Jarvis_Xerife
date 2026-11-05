"""Tests for the public camera layer used by the HUD camera window."""

from __future__ import annotations

import pytest

from app.adapters.edge import jarvis_open_cameras as cameras


@pytest.fixture(autouse=True)
def _clear_cache():
    cameras._CACHE.clear()
    yield
    cameras._CACHE.clear()


def _tfl_row(cam_id: str, lat: float, lon: float, image: str = "https://img/1.jpg") -> dict:
    return {
        "id": cam_id,
        "commonName": f"Camera {cam_id}",
        "lat": lat,
        "lon": lon,
        "additionalProperties": [
            {"key": "imageUrl", "value": image},
            {"key": "available", "value": "true"},
        ],
    }


def _datumfeed_row(cam_id: str, lat: float, lon: float) -> dict:
    return {
        "id": cam_id,
        "name": f"DF {cam_id}",
        "feedUrl": f"https://feed/{cam_id}.jpg",
        "latitude": lat,
        "longitude": lon,
        "verificationStatus": "auto_checked",
        "stats": {"trustScore": 80, "uptime24h": 0.9, "lastOkAt": "2026-11-05T10:00:00Z"},
        "registry": {
            "city": "Austin",
            "country": "US",
            "attribution": "Camera: Austin TX DOT",
            "licenseName": "Public domain",
            "licenseUrl": "https://example/license",
            "proxyOk": True,
            "minPollIntervalS": 60,
        },
    }


def test_cameras_are_filtered_by_radius_and_sorted_by_distance(monkeypatch):
    monkeypatch.setattr(
        cameras,
        "_fetch_json",
        lambda url, params=None: {
            cameras.TFL_URL: [
                _tfl_row("near", 51.5007, -0.1246),
                _tfl_row("far", 53.4808, -2.2426),
            ],
            cameras.DATUMFEED_URL: {"cameras": [], "total": 0},
        }[url],
    )

    payload = cameras.build_open_cameras(51.5074, -0.1278, radius_km=50, limit=10)

    assert payload["success"] is True
    assert payload["located"] is True
    assert [item["id"] for item in payload["cameras"]] == ["tfl:near"]
    assert payload["total"] == 1
    assert payload["cameras"][0]["distance_km"] < 5
    assert payload["cameras"][0]["attribution"].startswith("© Transport for London")
    assert payload["cameras"][0]["license"] == "TfL Open Data terms"
    assert payload["cameras"][0]["provider"] == "tfl"


def test_datumfeed_cameras_carry_registry_attribution_and_refresh(monkeypatch):
    monkeypatch.setattr(
        cameras,
        "_fetch_json",
        lambda url, params=None: (
            {"cameras": [_datumfeed_row("a1", 30.2672, -97.7431)], "total": 1}
            if url == cameras.DATUMFEED_URL
            else []
        ),
    )

    payload = cameras.build_open_cameras(30.2672, -97.7431, radius_km=40)

    camera = payload["cameras"][0]
    assert camera["provider"] == "datumfeed"
    assert camera["attribution"] == "Camera: Austin TX DOT"
    assert camera["license"] == "Public domain"
    assert camera["refresh_seconds"] == 60
    assert camera["place"] == {"city": "Austin", "state": None, "country": "US"}
    assert camera["live"]["status"] == "auto_checked"


def test_registry_without_proxy_permission_is_skipped(monkeypatch):
    row = _datumfeed_row("blocked", 30.2672, -97.7431)
    row["registry"]["proxyOk"] = False
    monkeypatch.setattr(
        cameras,
        "_fetch_json",
        lambda url, params=None: (
            {"cameras": [row]} if url == cameras.DATUMFEED_URL else []
        ),
    )

    payload = cameras.build_open_cameras(30.2672, -97.7431)

    assert payload["cameras"] == []
    assert payload["reason"] == "no_camera_in_radius"


def test_missing_location_reports_location_required_without_guessing(monkeypatch):
    monkeypatch.setattr(cameras, "_fetch_json", lambda url, params=None: [])

    payload = cameras.build_open_cameras(None, None)

    assert payload["located"] is False
    assert payload["reason"] == "location_required"
    assert payload["cameras"] == []
    assert payload["location"] is None


def test_provider_failure_is_reported_instead_of_invented(monkeypatch):
    def boom(url, params=None):
        raise cameras.httpx.ConnectError("down")

    monkeypatch.setattr(cameras, "_fetch_json", boom)

    payload = cameras.build_open_cameras(51.5074, -0.1278)

    providers = {provider["id"]: provider for provider in payload["providers"]}
    assert providers["tfl"]["available"] is False
    assert providers["tfl"]["error"] == "network"
    assert payload["cameras"] == []


def test_malformed_payload_is_not_treated_as_empty_coverage(monkeypatch):
    monkeypatch.setattr(cameras, "_fetch_json", lambda url, params=None: {"wat": 1})

    payload = cameras.build_open_cameras(51.5074, -0.1278)

    providers = {provider["id"]: provider for provider in payload["providers"]}
    assert providers["datumfeed"]["available"] is False
    assert providers["datumfeed"]["error"] == "malformed"


def test_limit_and_radius_are_bounded(monkeypatch):
    monkeypatch.setattr(
        cameras,
        "_fetch_json",
        lambda url, params=None: (
            [_tfl_row(str(index), 51.5, -0.12) for index in range(60)]
            if url == cameras.TFL_URL
            else {"cameras": []}
        ),
    )

    payload = cameras.build_open_cameras(51.5, -0.12, radius_km=9999, limit=500)

    assert payload["radius_km"] == cameras.MAX_RADIUS_KM
    assert len(payload["cameras"]) == cameras.MAX_CAMERAS
    assert len({item["id"] for item in payload["cameras"]}) == cameras.MAX_CAMERAS
