"""Read-only Shodan geo-filtered host search adapter for bounded L2 discovery."""
from __future__ import annotations

import ipaddress
import logging
from typing import Any, Callable

import httpx

from app.application.ports.osint_discovery import PassiveIntel
from app.domain.intelligence.osint import Coordinate, Host

logger = logging.getLogger(__name__)


class ShodanAdapter(PassiveIntel):
    """Query Shodan's indexed banners inside a radius and L1-authorized CIDRs."""

    SEARCH_URL = "https://api.shodan.io/shodan/host/search"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        api_key_provider: Callable[[], str | None] | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")
        self._client = client
        self._api_key_provider = api_key_provider
        self._timeout = timeout_seconds

    def query_radius(
        self, coord: Coordinate, radius_km: float, filters: dict[str, Any]
    ) -> tuple[Host, ...]:
        if not 0 < radius_km <= 500:
            raise ValueError("radius_km must be greater than 0 and at most 500")
        cidrs = filters.get("cidrs")
        if not isinstance(cidrs, (list, tuple)) or not cidrs:
            raise ValueError("Shodan discovery requires L1 CIDR ranges")
        if len(cidrs) > 10:
            raise ValueError("at most 10 L1 CIDR ranges may be queried per call")
        api_key = self._api_key_provider() if self._api_key_provider else None
        if not api_key:
            raise RuntimeError("Shodan API key is not configured")
        limit = filters.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")

        grouped: dict[str, dict[str, Any]] = {}
        for raw_cidr in cidrs:
            network = ipaddress.ip_network(raw_cidr, strict=False)
            query = (
                f"geo:{coord.lat},{coord.lon},{radius_km:g} "
                f"net:{network.with_prefixlen}"
            )
            payload = self._get(
                {"key": api_key, "query": query, "page": 1, "minify": True}
            )
            matches = payload.get("matches", [])
            if not isinstance(matches, list):
                raise RuntimeError("Shodan returned an invalid matches collection")
            for match in matches[:limit]:
                if not isinstance(match, dict):
                    continue
                ip = self._match_ip(match)
                if not ip:
                    continue
                record = grouped.setdefault(
                    ip,
                    {
                        "ports": set(),
                        "geo": self._coordinate(match.get("location")),
                        "org": match.get("org") or match.get("isp"),
                        "asn": match.get("asn"),
                        "country": (match.get("location") or {}).get("country_code")
                        if isinstance(match.get("location"), dict)
                        else None,
                        "hostnames": match.get("hostnames", []),
                    },
                )
                port = match.get("port")
                if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
                    record["ports"].add(port)

        return tuple(
            Host(
                ip=ip,
                ports=tuple(sorted(record["ports"])),
                geo=record["geo"],
                geo_confidence=0.6 if record["geo"] is not None else 0.0,
                sources=("shodan",),
                metadata={
                    "org": record["org"],
                    "asn": record["asn"],
                    "country": record["country"],
                    "hostnames": record["hostnames"][:20]
                    if isinstance(record["hostnames"], list)
                    else [],
                },
            )
            for ip, record in sorted(grouped.items())
        )

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = self._client.get(
                    self.SEARCH_URL, params=params, timeout=self._timeout
                )
                response.raise_for_status()
                payload = response.json()
            else:
                with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                    response = client.get(self.SEARCH_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Shodan query failed (%s)", type(exc).__name__)
            raise RuntimeError("Shodan query failed") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Shodan returned a non-object response")
        return payload

    @staticmethod
    def _match_ip(match: dict[str, Any]) -> str | None:
        value = match.get("ip_str")
        if isinstance(value, str):
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                return None
        numeric = match.get("ip")
        if isinstance(numeric, int) and not isinstance(numeric, bool):
            try:
                return str(ipaddress.IPv4Address(numeric))
            except ipaddress.AddressValueError:
                return None
        return None

    @staticmethod
    def _coordinate(location: Any) -> Coordinate | None:
        if not isinstance(location, dict):
            return None
        try:
            return Coordinate(
                lat=float(location["latitude"]),
                lon=float(location["longitude"]),
                accuracy_m=5000,
                source="shodan",
            )
        except (KeyError, TypeError, ValueError):
            return None
