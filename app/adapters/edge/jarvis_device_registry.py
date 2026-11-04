"""Read-only view of the registered devices for the Jarvis Desktop HUD.

The distributed core keeps every registered node in the ``devices`` table of
the local SQLite database (``Device`` model). The HUD needs name, type, status
and — when the node reported one — a position, so it can plot the device on the
globe. This module only ever reads: the database is opened with ``mode=ro`` and
the query is a fixed ``SELECT``. No row is created, updated or deleted, and no
network call is made.

A node without coordinates is still listed (``located: false``) so the operator
sees it; it simply cannot be drawn on the globe. Nothing is inferred: a missing
latitude is reported as missing rather than guessed from the IP address.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_DEVICES = 64
REPO_ROOT = Path(__file__).resolve().parents[3]

_COLUMNS = (
    "id",
    "name",
    "type",
    "status",
    "lat",
    "lon",
    "last_ip",
    "last_seen",
    "network_type",
    "network_id",
)


def devices_db_path() -> Path:
    """Database holding the device registry; overridable for tests and portable installs."""
    configured = os.getenv("JARVIS_DEVICES_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return REPO_ROOT / "jarvis.db"


def _coordinate(value: Any, limit: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if not -limit <= number <= limit:
        return None
    return round(number, 5)


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _normalize(row: sqlite3.Row) -> dict[str, Any]:
    latitude = _coordinate(row["lat"], 90.0)
    longitude = _coordinate(row["lon"], 180.0)
    located = latitude is not None and longitude is not None
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or "dispositivo")[:80],
        "type": str(row["type"] or "desconhecido")[:32],
        "status": str(row["status"] or "offline")[:24],
        "latitude": latitude,
        "longitude": longitude,
        "located": located,
        "last_ip": str(row["last_ip"])[:64] if row["last_ip"] else None,
        "last_seen": _timestamp(row["last_seen"]),
        "network_type": str(row["network_type"])[:16] if row["network_type"] else None,
        "network_id": str(row["network_id"])[:64] if row["network_id"] else None,
    }


def build_device_registry(path: Path | None = None) -> dict[str, Any]:
    """Return the registered devices without ever mutating the registry."""
    target = path or devices_db_path()
    payload: dict[str, Any] = {
        "success": True,
        "available": False,
        "source": "sqlite",
        "path": str(target),
        "devices": [],
        "total": 0,
        "located": 0,
        "reason": None,
        "hint": (
            "Os dispositivos vêm da tabela devices do núcleo distribuído. "
            "Cadastre-os pelo serviço de dispositivos para que apareçam no globo."
        ),
    }
    if not target.is_file():
        payload.update({"success": False, "reason": "database_missing"})
        return payload

    uri = f"file:{target.as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        payload.update({"success": False, "reason": type(exc).__name__})
        return payload
    try:
        connection.row_factory = sqlite3.Row
        query = f"SELECT {', '.join(_COLUMNS)} FROM devices ORDER BY id LIMIT {MAX_DEVICES}"
        rows = connection.execute(query).fetchall()
    except sqlite3.Error as exc:
        payload.update({"success": False, "reason": type(exc).__name__})
        return payload
    finally:
        connection.close()

    devices = [_normalize(row) for row in rows]
    payload.update(
        {
            "available": True,
            "devices": devices,
            "total": len(devices),
            "located": sum(1 for device in devices if device["located"]),
        }
    )
    return payload
