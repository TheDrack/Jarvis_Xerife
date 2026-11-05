"""Read-only Censys Platform host search adapter for bounded L2 discovery."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any, Callable

import httpx

from app.application.ports.osint_discovery import PassiveIntel
from app.domain.intelligence.osint import Coordinate, Host

logger = logging.getLogger(__name__)


class CensysAdapter(PassiveIntel):
    """Query Censys host records within a radius and L1-authorized CIDR ranges."""

    SEARCH_URL = "https://api.platform.censys.io/v3/global/search/query"
    FIELDS = [
        "host.ip",
        "host.location.coordinates",
        "host.location.country",
        "host.autonomous_system.asn",
        "host.autonomous_system.organization",
        "host.services.port",
        "host.services.protocol",
        "host.services.scan_time",
    ]

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        token_provider: Callable[[], str | None] | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")
        self._client = client
        self._token_provider = token_provider
        self._timeout = timeout_seconds

    def query_radius(
        self, coord: Coordinate, radius_km: float, filters: dict[str, Any]
    ) -> tuple[Host, ...]:
        if not 0 < radius_km <= 500:
            raise ValueError("radius_km must be greater than 0 and at most 500")
        cidrs = filters.get("cidrs")
        if not isinstance(cidrs, (list, tuple)) or not cidrs:
            raise ValueError("Censys discovery requires L1 CIDR ranges")

        token = self._token_provider() if self._token_provider else None
        if not token:
            raise RuntimeError("Censys API token is not configured")

        query = self._build_query(coord, radius_km, cidrs)
        limit = filters.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        payload = self._post(
            {"query": query, "page_size": limit, "fields": self.FIELDS},
            token,
        )
        result = payload.get("result", payload)
        hits = result.get("hits", []) if isinstance(result, dict) else []
        if not isinstance(hits, list):
            raise RuntimeError("Censys returned an invalid hits collection")

        hosts: list[Host] = []
        for hit in hits[:limit]:
            if not isinstance(hit, dict):
                continue
            record = hit.get("host") if isinstance(hit.get("host"), dict) else hit
            ip = record.get("ip")
            if not isinstance(ip, str):
                continue
            location = record.get("location") or {}
            coordinates = location.get("coordinates") if isinstance(location, dict) else None
            geo = self._coordinate(coordinates)
            services = record.get("services") or hit.get("matched_services") or []
            ports = tuple(
                int(item["port"])
                for item in services
                if isinstance(item, dict)
                and isinstance(item.get("port"), int)
                and 1 <= item["port"] <= 65535
            )
            hosts.append(
                Host(
                    ip=ip,
                    ports=ports,
                    geo=geo,
                    geo_confidence=0.55 if geo is not None else 0.0,
                    sources=("censys",),
                    metadata={
                        "country": location.get("country") if isinstance(location, dict) else None,
                        "autonomous_system": record.get("autonomous_system"),
                        "service_count": len(services) if isinstance(services, list) else 0,
                    },
                )
            )
        return tuple(hosts)

    @staticmethod
    def _build_query(
        coord: Coordinate, radius_km: float, cidrs: list[str] | tuple[str, ...]
    ) -> str:
        ranges: list[str] = []
        for value in cidrs:
            network = ipaddress.ip_network(value, strict=False)
            ranges.append(
                f'(host.ip >= "{network.network_address}" and '
                f'host.ip <= "{network.broadcast_address}")'
            )
        range_query = " or ".join(ranges)
        return (
            f"geo_distance(host.location.coordinates,{coord.lat},{coord.lon},"
            f"{radius_km:g}km) and ({range_query})"
        )

    def _post(self, body: dict[str, Any], token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            if self._client is not None:
                response = self._client.post(
                    self.SEARCH_URL, json=body, headers=headers, timeout=self._timeout
                )
                response.raise_for_status()
                payload = response.json()
            else:
                with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                    response = client.post(self.SEARCH_URL, json=body, headers=headers)
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Censys query failed (%s)", type(exc).__name__)
            raise RuntimeError("Censys query failed") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Censys returned a non-object response")
        return payload

    @staticmethod
    def _coordinate(value: Any) -> Coordinate | None:
        if isinstance(value, dict):
            latitude, longitude = value.get("latitude"), value.get("longitude")
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            latitude, longitude = value[0], value[1]
        else:
            return None
        try:
            return Coordinate(
                lat=float(latitude),
                lon=float(longitude),
                accuracy_m=5000,
                source="censys",
            )
        except (TypeError, ValueError):
            return None
