"""Bounded geospatial filtering and an auditable watchlist for registered devices."""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EARTH_RADIUS_KM = 6371.0088
MAX_VIEW_RADIUS_KM = math.pi * EARTH_RADIUS_KM


def _number(value: Any, limit: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or not -limit <= result <= limit:
        return None
    return result


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance using the haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(value)))


def filter_assets_by_radius(
    assets: Iterable[dict[str, Any]],
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[dict[str, Any]]:
    """Return only located assets inside a validated circular viewport."""
    center_lat = _number(latitude, 90.0)
    center_lon = _number(longitude, 180.0)
    radius = _number(radius_km, MAX_VIEW_RADIUS_KM)
    if center_lat is None or center_lon is None or radius is None or radius <= 0:
        raise ValueError("viewport coordinates and radius are invalid")
    matches: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("located") is not True:
            continue
        lat = _number(asset.get("latitude"), 90.0)
        lon = _number(asset.get("longitude"), 180.0)
        if lat is None or lon is None:
            continue
        distance = distance_km(center_lat, center_lon, lat, lon)
        if distance <= radius:
            item = dict(asset)
            item["distance_km"] = round(distance, 2)
            matches.append(item)
    return sorted(matches, key=lambda item: item["distance_km"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _asset_id(asset_id: Any) -> int:
    try:
        value = int(asset_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("asset must be a registered device") from exc
    if value <= 0:
        raise ValueError("asset must be a registered device with a stable positive ID")
    return value


def _location_confidence(asset: dict[str, Any]) -> str:
    if asset.get("location_source") == "ip" or asset.get("approximate"):
        return "low"
    if asset.get("location_source") == "gps":
        return "high"
    return "none"


class GeospatialWatchlistStore:
    """Persist selected registered devices and changes without inferring movement."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE IF NOT EXISTS geospatial_watchlist (
                asset_id INTEGER PRIMARY KEY CHECK(asset_id > 0),
                name TEXT NOT NULL,
                device_type TEXT,
                status TEXT,
                last_ip TEXT,
                latitude REAL,
                longitude REAL,
                location_source TEXT,
                approximate INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                added_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_change_at TEXT,
                last_change_type TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS geospatial_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                change_type TEXT NOT NULL,
                previous_ip TEXT,
                current_ip TEXT,
                latitude REAL,
                longitude REAL,
                location_source TEXT,
                approximate INTEGER NOT NULL DEFAULT 0,
                movement_inferred INTEGER NOT NULL DEFAULT 0,
                location_confidence TEXT NOT NULL,
                details_json TEXT NOT NULL
            )"""
        )
        return connection

    @staticmethod
    def _values(asset: dict[str, Any]) -> dict[str, Any]:
        identifier = _asset_id(asset.get("id", asset.get("asset_id")))
        lat = _number(asset.get("latitude"), 90.0)
        lon = _number(asset.get("longitude"), 180.0)
        if lat is None or lon is None:
            lat = lon = None
        return {
            "asset_id": identifier,
            "name": str(asset.get("name") or f"Dispositivo {identifier}")[:80],
            "device_type": str(asset.get("type") or "desconhecido")[:32],
            "status": str(asset.get("status") or "unknown")[:24],
            "last_ip": str(asset.get("last_ip") or "")[:64] or None,
            "latitude": lat,
            "longitude": lon,
            "location_source": str(asset.get("location_source") or "")[:16] or None,
            "approximate": int(bool(asset.get("approximate"))),
            "source": str(asset.get("source") or "device_registry")[:40],
        }

    @staticmethod
    def _append_observation(
        connection: sqlite3.Connection,
        values: dict[str, Any],
        *,
        change_type: str,
        previous_ip: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        asset = {
            "location_source": values.get("location_source"),
            "approximate": bool(values.get("approximate")),
        }
        connection.execute(
            """INSERT INTO geospatial_observations (
                asset_id, observed_at, change_type, previous_ip, current_ip,
                latitude, longitude, location_source, approximate,
                movement_inferred, location_confidence, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                values["asset_id"], _now(), change_type, previous_ip,
                values.get("last_ip"), values.get("latitude"), values.get("longitude"),
                values.get("location_source"), values.get("approximate", 0),
                _location_confidence(asset),
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["approximate"] = bool(result.get("approximate"))
        return result

    def add(self, asset: dict[str, Any]) -> dict[str, Any]:
        values = self._values(asset)
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT asset_id FROM geospatial_watchlist WHERE asset_id = ?",
                (values["asset_id"],),
            ).fetchone()
            if existing:
                return self._row(connection.execute(
                    "SELECT * FROM geospatial_watchlist WHERE asset_id = ?",
                    (values["asset_id"],),
                ).fetchone())
            now = _now()
            columns = (
                "asset_id", "name", "device_type", "status", "last_ip",
                "latitude", "longitude", "location_source", "approximate",
                "source", "added_at", "last_seen_at",
            )
            connection.execute(
                f"INSERT INTO geospatial_watchlist ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(values[key] for key in columns[:10]) + (now, now),
            )
            self._append_observation(
                connection, values, change_type="added",
                details={"source": values["source"]},
            )
            row = connection.execute(
                "SELECT * FROM geospatial_watchlist WHERE asset_id = ?",
                (values["asset_id"],),
            ).fetchone()
            return self._row(row)

    def observe(self, asset: dict[str, Any]) -> dict[str, Any]:
        values = self._values(asset)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM geospatial_watchlist WHERE asset_id = ?",
                (values["asset_id"],),
            ).fetchone()
            if row is None:
                raise KeyError(values["asset_id"])
            previous = dict(row)
            changed_fields = []
            for key in ("last_ip", "latitude", "longitude", "location_source", "approximate", "status"):
                old_value = previous.get(key)
                new_value = values.get(key)
                if key in {"latitude", "longitude"} and old_value is not None and new_value is not None:
                    different = abs(float(old_value) - float(new_value)) >= 0.001
                else:
                    different = old_value != new_value
                if different:
                    changed_fields.append(key)
            if not changed_fields:
                connection.execute(
                    "UPDATE geospatial_watchlist SET last_seen_at = ?, name = ?, device_type = ? WHERE asset_id = ?",
                    (_now(), values["name"], values["device_type"], values["asset_id"]),
                )
                return {"changed": False, "change_type": None, "asset_id": values["asset_id"]}

            if "last_ip" in changed_fields:
                change_type = "ip_changed"
            elif {"latitude", "longitude"} & set(changed_fields):
                change_type = "location_estimate_changed" if (
                    previous.get("location_source") == "ip" or values.get("location_source") == "ip"
                    or previous.get("approximate") or values.get("approximate")
                ) else "gps_position_changed"
            else:
                change_type = "status_changed"
            self._append_observation(
                connection, values, change_type=change_type,
                previous_ip=previous.get("last_ip"),
                details={
                    "changed_fields": changed_fields,
                    "previous_latitude": previous.get("latitude"),
                    "previous_longitude": previous.get("longitude"),
                    "current_latitude": values.get("latitude"),
                    "current_longitude": values.get("longitude"),
                    "interpretation": "ip_change_is_not_device_movement",
                },
            )
            now = _now()
            connection.execute(
                """UPDATE geospatial_watchlist SET
                    name = ?, device_type = ?, status = ?, last_ip = ?,
                    latitude = ?, longitude = ?, location_source = ?,
                    approximate = ?, source = ?, last_seen_at = ?,
                    last_change_at = ?, last_change_type = ?
                    WHERE asset_id = ?""",
                (
                    values["name"], values["device_type"], values["status"],
                    values["last_ip"], values["latitude"], values["longitude"],
                    values["location_source"], values["approximate"], values["source"],
                    now, now, change_type, values["asset_id"],
                ),
            )
            return {
                "changed": True,
                "change_type": change_type,
                "asset_id": values["asset_id"],
                "changed_fields": changed_fields,
                "movement_inferred": False,
                "location_confidence": _location_confidence(values),
            }

    def list_assets(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT * FROM geospatial_watchlist ORDER BY last_seen_at DESC, asset_id"
            ).fetchall()
            return [self._row(row) for row in rows]

    def history(self, asset_id: int, limit: int = 100) -> list[dict[str, Any]]:
        identifier = _asset_id(asset_id)
        bounded_limit = max(1, min(int(limit), 500))
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """SELECT * FROM (
                       SELECT * FROM geospatial_observations
                       WHERE asset_id = ? ORDER BY id DESC LIMIT ?
                   ) ORDER BY id ASC""",
                (identifier, bounded_limit),
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["approximate"] = bool(item["approximate"])
                item["movement_inferred"] = bool(item["movement_inferred"])
                item["details"] = json.loads(item.pop("details_json") or "{}")
                results.append(item)
            return results

    def remove(self, asset_id: int) -> bool:
        identifier = _asset_id(asset_id)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "DELETE FROM geospatial_watchlist WHERE asset_id = ?", (identifier,)
            )
            return cursor.rowcount > 0
