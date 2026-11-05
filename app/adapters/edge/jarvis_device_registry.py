"""Read-only view of the registered devices for the Jarvis Desktop HUD.

The distributed core keeps every registered node in the ``devices`` table of
the local SQLite database (``Device`` model). The HUD needs name, type, status
and — when the node reported one — a position, so it can plot the device on the
globe. This module only ever reads: the database is opened with ``mode=ro`` and
the query is a fixed ``SELECT``. No row is created, updated or deleted.

Position comes from two sources, always labelled:

* ``gps`` — the latitude/longitude stored by the node itself;
* ``ip`` — the last reported public IP resolved to an approximate city by the
  public ipwho.is service. This is opt-out (``JARVIS_IP_GEOLOCATION=off``),
  never used for private, loopback, link-local or CGNAT addresses, and marked
  ``approximate`` because it points at the ISP's city, not the device.

Reverse geocoding of the GPS coordinates supplies ``city``/``state``/``country``
through the same Nominatim helper used by the briefing. A node without a
position is still listed (``located: false``) so the operator sees it; nothing
is inferred without a source and a reason is reported instead.
"""

from __future__ import annotations

import ipaddress
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

MAX_DEVICES = 64
REPO_ROOT = Path(__file__).resolve().parents[3]
IP_GEOLOCATION_URL = "https://ipwho.is/{ip}"
IP_GEOLOCATION_TTL_SECONDS = 86400.0
IP_GEOLOCATION_TIMEOUT_SECONDS = 8.0
IP_GEOLOCATION_MAX_ENTRIES = 256

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

_IP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_NON_PUBLIC_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
        "0.0.0.0/8",
        "224.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def devices_db_path() -> Path:
    """Database holding the device registry; overridable for tests and portable installs."""
    configured = os.getenv("JARVIS_DEVICES_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    return REPO_ROOT / "jarvis.db"


def ip_geolocation_enabled() -> bool:
    """IP lookups are opt-out: they send the device's public IP to a third party."""
    return os.getenv("JARVIS_IP_GEOLOCATION", "").strip().lower() not in {
        "off",
        "0",
        "false",
        "no",
    }


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


def public_ip(value: Any) -> str | None:
    """Return the address only when it is a routable public IP we may look up."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or len(text) > 64:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if any(address in network for network in _NON_PUBLIC_NETWORKS):
        return None
    if not address.is_global:
        return None
    return str(address)


def lookup_ip(ip: str) -> dict[str, Any]:
    """Resolve a public IP to an approximate place; cached for a day per address."""
    now = time.monotonic()
    cached = _IP_CACHE.get(ip)
    if cached and now - cached[0] < IP_GEOLOCATION_TTL_SECONDS:
        return cached[1]
    if len(_IP_CACHE) >= IP_GEOLOCATION_MAX_ENTRIES:
        oldest = min(_IP_CACHE, key=lambda key: _IP_CACHE[key][0])
        _IP_CACHE.pop(oldest, None)
    try:
        response = httpx.get(
            IP_GEOLOCATION_URL.format(ip=ip),
            timeout=IP_GEOLOCATION_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "Jarvis-Xerife/0.1"},
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        result = {"available": False, "reason": type(exc).__name__}
        _IP_CACHE[ip] = (now, result)
        return result
    if not isinstance(data, dict) or not data.get("success", True):
        result = {"available": False, "reason": "no_result"}
        _IP_CACHE[ip] = (now, result)
        return result
    latitude = _coordinate(data.get("latitude"), 90.0)
    longitude = _coordinate(data.get("longitude"), 180.0)
    if latitude is None or longitude is None:
        result = {"available": False, "reason": "no_coordinate"}
        _IP_CACHE[ip] = (now, result)
        return result
    result = {
        "available": True,
        "latitude": latitude,
        "longitude": longitude,
        "place": {
            "city": data.get("city"),
            "state": data.get("region"),
            "country": data.get("country"),
        },
        "isp": (data.get("connection") or {}).get("isp"),
        "source": "ipwho.is",
    }
    _IP_CACHE[ip] = (now, result)
    return result


def _place_from(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    place = {
        "city": value.get("city") or None,
        "state": value.get("state") or None,
        "country": value.get("country") or None,
    }
    return place if any(place.values()) else None


def place_label(place: dict[str, Any] | None) -> str | None:
    """Render ``cidade · estado · país`` with the parts that are known."""
    if not isinstance(place, dict):
        return None
    parts = [str(place[key]) for key in ("city", "state", "country") if place.get(key)]
    return " · ".join(parts)[:80] if parts else None


def _base(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or "dispositivo")[:80],
        "type": str(row["type"] or "desconhecido")[:32],
        "status": str(row["status"] or "offline")[:24],
        "latitude": _coordinate(row["lat"], 90.0),
        "longitude": _coordinate(row["lon"], 180.0),
        "last_ip": str(row["last_ip"])[:64] if row["last_ip"] else None,
        "last_seen": _timestamp(row["last_seen"]),
        "network_type": str(row["network_type"])[:16] if row["network_type"] else None,
        "network_id": str(row["network_id"])[:64] if row["network_id"] else None,
    }


def _enrich(
    device: dict[str, Any],
    *,
    geocoder: Callable[[float, float], dict[str, Any]] | None,
    ip_lookup: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Attach the position source, the place names and an honest reason."""
    device.update(
        {
            "located": False,
            "location_source": None,
            "approximate": False,
            "place": None,
            "place_label": None,
            "location_reason": None,
        }
    )
    latitude, longitude = device["latitude"], device["longitude"]
    if latitude is not None and longitude is not None:
        device.update(
            {
                "located": True,
                "location_source": "gps",
                "approximate": False,
            }
        )
        if geocoder is not None:
            result = geocoder(latitude, longitude)
            if isinstance(result, dict) and result.get("available"):
                place = _place_from(result)
                if place:
                    device["place"] = place
                    device["place_label"] = place_label(place)
            else:
                device["location_reason"] = str(
                    (result or {}).get("reason") or "geocode_unavailable"
                )
        return device

    if not device["last_ip"]:
        device["location_reason"] = "no_position"
        return device
    if ip_lookup is None:
        device["location_reason"] = "ip_lookup_disabled"
        return device
    address = public_ip(device["last_ip"])
    if address is None:
        device["location_reason"] = "non_public_ip"
        return device
    result = ip_lookup(address)
    if not isinstance(result, dict) or not result.get("available"):
        device["location_reason"] = str((result or {}).get("reason") or "ip_unavailable")
        return device
    place = _place_from(result.get("place"))
    device.update(
        {
            "latitude": result.get("latitude"),
            "longitude": result.get("longitude"),
            "located": True,
            "location_source": "ip",
            "approximate": True,
            "place": place,
            "place_label": place_label(place),
            "location_reason": "public_ip",
            "ip_isp": result.get("isp"),
        }
    )
    return device


def build_device_registry(
    path: Path | None = None,
    *,
    geocoder: Callable[[float, float], dict[str, Any]] | None = None,
    ip_lookup: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
        "located_gps": 0,
        "located_ip": 0,
        "geocoded": False,
        "ip_geolocation": ip_geolocation_enabled(),
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

    # Network lookups are wired by the caller (the local API route): this module
    # stays deterministic and read-only on its own.

    devices = [
        _enrich(_base(row), geocoder=geocoder, ip_lookup=ip_lookup) for row in rows
    ]
    payload.update(
        {
            "available": True,
            "devices": devices,
            "total": len(devices),
            "located": sum(1 for device in devices if device["located"]),
            "located_gps": sum(
                1 for device in devices if device["location_source"] == "gps"
            ),
            "located_ip": sum(
                1 for device in devices if device["location_source"] == "ip"
            ),
            "geocoded": any(device["place"] for device in devices),
        }
    )
    return payload
