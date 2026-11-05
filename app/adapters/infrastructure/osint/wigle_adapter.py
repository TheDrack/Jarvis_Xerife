"""WiGLE historical wireless-network discovery adapter.

The provider's bounding-box API is converted internally from the shared
center-plus-radius port contract. Results remain Signal entities, never Hosts.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Callable

import httpx

from app.application.ports.osint_discovery import PassiveIntel
from app.domain.intelligence.osint import Coordinate, Signal

logger = logging.getLogger(__name__)


class WigleAdapter(PassiveIntel):
    """Search Wi-Fi and Bluetooth observations in WiGLE's historical database."""

    BASE_URL = "https://api.wigle.net/api/v2"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        username_provider: Callable[[], str | None] | None = None,
        token_provider: Callable[[], str | None] | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")
        self._client = client
        self._username_provider = username_provider
        self._token_provider = token_provider
        self._timeout = timeout_seconds

    def query_radius(
        self, coord: Coordinate, radius_km: float, filters: dict[str, Any]
    ) -> tuple[Signal, ...]:
        if not 0 < radius_km <= 100:
            raise ValueError("WiGLE radius_km must be greater than 0 and at most 100")
        kind = filters.get("kind", "wifi")
        if kind not in {"wifi", "bluetooth", "all"}:
            raise ValueError("kind must be wifi, bluetooth, or all")
        limit = filters.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")

        username = self._username_provider() if self._username_provider else None
        token = self._token_provider() if self._token_provider else None
        if not username or not token:
            raise RuntimeError("WiGLE username and API token are required")

        kinds = ("wifi", "bluetooth") if kind == "all" else (kind,)
        signals: dict[tuple[str, str], Signal] = {}
        for signal_kind in kinds:
            endpoint = "network/search" if signal_kind == "wifi" else "bluetooth/search"
            for south, north, west, east in self._bounding_boxes(coord, radius_km):
                payload = self._get(
                    endpoint,
                    {
                        "latrange1": south,
                        "latrange2": north,
                        "longrange1": west,
                        "longrange2": east,
                        "resultsPerPage": limit,
                        "variance": 0.001,
                    },
                    auth=(username, token),
                )
                results = payload.get("results", [])
                if not isinstance(results, list):
                    raise RuntimeError("WiGLE returned an invalid results collection")
                for item in results[:limit]:
                    signal = self._to_signal(signal_kind, item)
                    if signal is not None:
                        signals[(signal.kind, signal.identifier)] = signal
        return tuple(signals[key] for key in sorted(signals))

    def _get(
        self, endpoint: str, params: dict[str, Any], *, auth: tuple[str, str]
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            if self._client is not None:
                response = self._client.get(
                    url, params=params, auth=auth, timeout=self._timeout
                )
                response.raise_for_status()
                payload = response.json()
            else:
                with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                    response = client.get(url, params=params, auth=auth)
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("WiGLE query failed (%s)", type(exc).__name__)
            raise RuntimeError("WiGLE query failed") from exc
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise RuntimeError("WiGLE returned an unsuccessful response")
        return payload

    @staticmethod
    def _bounding_boxes(
        coord: Coordinate, radius_km: float
    ) -> tuple[tuple[float, float, float, float], ...]:
        lat_delta = radius_km / 110.574
        cosine = abs(math.cos(math.radians(coord.lat)))
        lon_delta = 180.0 if cosine < 1e-6 else radius_km / (111.320 * cosine)
        south = max(-90.0, coord.lat - lat_delta)
        north = min(90.0, coord.lat + lat_delta)
        west, east = coord.lon - lon_delta, coord.lon + lon_delta
        if west < -180:
            return (
                (south, north, -180.0, east),
                (south, north, west + 360.0, 180.0),
            )
        if east > 180:
            return (
                (south, north, west, 180.0),
                (south, north, -180.0, east - 360.0),
            )
        return ((south, north, west, east),)

    @staticmethod
    def _to_signal(kind: str, item: Any) -> Signal | None:
        if not isinstance(item, dict):
            return None
        identifier = item.get("netid") if kind == "wifi" else item.get("mac")
        if not isinstance(identifier, str) or not identifier.strip():
            return None
        latitude = item.get("trilat")
        longitude = item.get("trilong")
        geo = None
        if latitude is not None and longitude is not None:
            try:
                geo = Coordinate(
                    lat=float(latitude),
                    lon=float(longitude),
                    accuracy_m=100,
                    source="wigle",
                )
            except (TypeError, ValueError):
                geo = None
        metadata = {
            key: item.get(key)
            for key in ("ssid", "name", "encryption", "qos", "channel", "lastupdt")
            if item.get(key) is not None
        }
        return Signal(
            kind=kind,
            identifier=identifier.strip().upper(),
            geo=geo,
            metadata=metadata,
            source="wigle",
        )
