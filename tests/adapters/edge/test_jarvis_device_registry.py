"""Tests for the read-only device registry that feeds the HUD globe."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.adapters.edge.jarvis_device_registry import (
    MAX_DEVICES,
    build_device_registry,
    devices_db_path,
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
