"""Tests for the read-only device registry that feeds the HUD globe."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.adapters.edge.jarvis_device_registry import (
    MAX_DEVICES,
    build_device_registry,
    devices_db_path,
    ip_geolocation_enabled,
    lookup_ip,
    public_ip,
)


def _database(path: Path, rows: list[tuple]) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE devices (id INTEGER PRIMARY KEY, name TEXT, type TEXT, status TEXT,"
            " lat REAL, lon REAL, last_ip TEXT, last_seen TEXT, network_type TEXT,"
            " network_id TEXT)"
        )
        connection.executemany(
            "INSERT INTO devices (id, name, type, status, lat, lon, last_ip, last_seen,"
            " network_type, network_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_missing_database_is_reported_without_raising(tmp_path: Path):
    payload = build_device_registry(tmp_path / "absent.db")

    assert payload["success"] is False
    assert payload["available"] is False
    assert payload["reason"] == "database_missing"
    assert payload["devices"] == []


def test_missing_table_is_reported_as_a_reason(tmp_path: Path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()

    payload = build_device_registry(path)

    assert payload["success"] is False
    assert payload["available"] is False
    assert payload["reason"] == "OperationalError"


def test_devices_are_read_with_position_and_status(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [
            (1, "Pixel 8", "mobile", "online", -30.0346, -51.2177, "192.168.0.15",
             "2026-11-01T10:20:30+00:00", "wifi", "casa"),
            (2, "Notebook", "desktop", "offline", None, None, None, None, None, None),
        ],
    )

    payload = build_device_registry(path)

    assert payload["success"] is True
    assert payload["available"] is True
    assert payload["total"] == 2
    assert payload["located"] == 1
    phone, notebook = payload["devices"]
    assert phone["name"] == "Pixel 8"
    assert phone["located"] is True
    assert phone["latitude"] == pytest.approx(-30.0346)
    assert phone["longitude"] == pytest.approx(-51.2177)
    assert phone["status"] == "online"
    assert phone["network_type"] == "wifi"
    assert notebook["located"] is False
    assert notebook["latitude"] is None
    assert notebook["longitude"] is None


def test_invalid_coordinates_are_dropped_instead_of_guessed(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [
            (1, "Fora do planeta", "mobile", "online", 120.0, -51.0, None, None, None, None),
            (2, "Sem texto", "mobile", "online", "abc", "def", None, None, None, None),
            (3, "Metade", "mobile", "online", -30.0, None, None, None, None, None),
            (4, "Ok", "mobile", "online", -30.0, -51.0, None, None, None, None),
        ],
    )

    payload = build_device_registry(path)

    assert [device["located"] for device in payload["devices"]] == [False, False, False, True]
    assert payload["located"] == 1
    assert payload["devices"][0]["latitude"] is None


def test_registry_is_opened_read_only_and_leaves_the_file_untouched(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [(1, "Pixel 8", "mobile", "online", -30.0, -51.0, None, None, None, None)],
    )
    before = path.read_bytes()

    build_device_registry(path)

    assert path.read_bytes() == before
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 1
    finally:
        connection.close()
    assert not list(tmp_path.glob("*.db-journal"))


def test_registry_is_capped(tmp_path: Path):
    rows = [
        (index, f"Device {index}", "mobile", "online", None, None, None, None, None, None)
        for index in range(1, MAX_DEVICES + 6)
    ]
    payload = build_device_registry(_database(tmp_path / "devices.db", rows))

    assert payload["total"] == MAX_DEVICES
    assert payload["devices"][-1]["id"] == MAX_DEVICES


def test_database_path_honours_the_environment_override(monkeypatch, tmp_path: Path):
    target = tmp_path / "custom.db"
    monkeypatch.setenv("JARVIS_DEVICES_DB", str(target))

    assert devices_db_path() == target


def test_database_path_defaults_to_the_repository_database(monkeypatch):
    monkeypatch.delenv("JARVIS_DEVICES_DB", raising=False)

    assert devices_db_path().name == "jarvis.db"


def _gps_database(tmp_path: Path, last_ip: str | None = None) -> Path:
    return _database(
        tmp_path / "devices.db",
        [(1, "Pixel 8", "mobile", "online", -25.4284, -49.2733, last_ip, None, "wifi", "casa")],
    )


def test_gps_position_is_named_by_the_injected_geocoder(tmp_path: Path):
    payload = build_device_registry(
        _gps_database(tmp_path),
        geocoder=lambda lat, lon: {
            "available": True,
            "city": "Curitiba",
            "state": "Paraná",
            "country": "Brasil",
        },
    )

    device = payload["devices"][0]
    assert device["location_source"] == "gps"
    assert device["approximate"] is False
    assert device["place"] == {
        "city": "Curitiba",
        "state": "Paraná",
        "country": "Brasil",
    }
    assert device["place_label"] == "Curitiba · Paraná · Brasil"
    assert payload["located_gps"] == 1
    assert payload["located_ip"] == 0
    assert payload["geocoded"] is True


def test_geocoder_failure_is_reported_without_inventing_a_place(tmp_path: Path):
    payload = build_device_registry(
        _gps_database(tmp_path),
        geocoder=lambda lat, lon: {"available": False, "reason": "timeout"},
    )

    device = payload["devices"][0]
    assert device["located"] is True
    assert device["place"] is None
    assert device["place_label"] is None
    assert device["location_reason"] == "timeout"


def test_public_ip_is_used_when_gps_is_missing(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [(1, "Notebook", "desktop", "online", None, None, "8.8.8.8", None, None, None)],
    )
    calls: list[str] = []

    def fake_lookup(ip: str) -> dict:
        calls.append(ip)
        return {
            "available": True,
            "latitude": 37.3394,
            "longitude": -121.895,
            "place": {"city": "San Jose", "state": "California", "country": "United States"},
            "isp": "Google LLC",
        }

    payload = build_device_registry(path, ip_lookup=fake_lookup)

    device = payload["devices"][0]
    assert calls == ["8.8.8.8"]
    assert device["located"] is True
    assert device["location_source"] == "ip"
    assert device["approximate"] is True
    assert device["latitude"] == pytest.approx(37.3394)
    assert device["place_label"] == "San Jose · California · United States"
    assert device["ip_isp"] == "Google LLC"
    assert payload["located_ip"] == 1


def test_private_ip_is_never_sent_to_a_lookup_service(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [(1, "TV", "iot", "online", None, None, "192.168.0.42", None, None, None)],
    )
    calls: list[str] = []

    payload = build_device_registry(
        path, ip_lookup=lambda ip: calls.append(ip) or {"available": True}
    )

    assert calls == []
    assert payload["devices"][0]["located"] is False
    assert payload["devices"][0]["location_reason"] == "non_public_ip"


def test_ip_lookup_failure_keeps_the_device_unlocated_with_a_reason(tmp_path: Path):
    path = _database(
        tmp_path / "devices.db",
        [(1, "TV", "iot", "online", None, None, "8.8.4.4", None, None, None)],
    )

    payload = build_device_registry(
        path, ip_lookup=lambda ip: {"available": False, "reason": "timeout"}
    )

    device = payload["devices"][0]
    assert device["located"] is False
    assert device["latitude"] is None
    assert device["location_reason"] == "timeout"


def test_public_ip_rejects_non_routable_and_invalid_values():
    for value in (
        None,
        "",
        "192.168.0.10",
        "10.1.2.3",
        "127.0.0.1",
        "100.64.1.1",
        "169.254.1.1",
        "fe80::1",
        "not-an-ip",
    ):
        assert public_ip(value) is None, value
    assert public_ip("8.8.8.8") == "8.8.8.8"


def test_ip_geolocation_is_opt_out(monkeypatch):
    monkeypatch.delenv("JARVIS_IP_GEOLOCATION", raising=False)
    assert ip_geolocation_enabled() is True
    monkeypatch.setenv("JARVIS_IP_GEOLOCATION", "off")
    assert ip_geolocation_enabled() is False


def test_lookup_ip_reports_transport_failure_without_raising(monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.adapters.edge.jarvis_device_registry.httpx.get", boom)

    result = lookup_ip("203.0.113.9")

    assert result["available"] is False
    assert result["reason"] == "ConnectError"
