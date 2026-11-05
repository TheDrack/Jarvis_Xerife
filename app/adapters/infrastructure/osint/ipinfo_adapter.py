"""IPinfo implementation of the L1 geo and network-resolution ports.

The adapter is deliberately stateless: cache, quotas, orchestration and telemetry
belong to application-level decorators/services, not to this provider adapter.
"""
from __future__ import annotations

import ipaddress
import logging
import re
from typing import Callable, Any

import httpx

from app.application.ports.osint_discovery import GeoProvider, NetworkResolver
from app.domain.intelligence.osint import Coordinate, GeoLocation, NetworkRange

logger = logging.getLogger(__name__)


class IPInfoAdapter(GeoProvider, NetworkResolver):
    """Resolve seed-IP geolocation and ASN/CIDR context through IPinfo."""

    BASE_URL = "https://ipinfo.io"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        token_provider: Callable[[], str | None] | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        if not 0 < timeout_seconds <= 20:
            raise ValueError("timeout_seconds must be between 0 and 20")
        self._client = client
        self._token_provider = token_provider
        self._timeout = timeout_seconds

    def locate(self, ip: str) -> GeoLocation:
        payload = self._lookup(ip)
        coordinate = self._coordinate(payload)
        privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
        company = payload.get("company") if isinstance(payload.get("company"), dict) else {}
        asn = payload.get("asn") if isinstance(payload.get("asn"), dict) else {}
        carrier = payload.get("carrier") if isinstance(payload.get("carrier"), dict) else {}

        is_proxy = any(bool(privacy.get(key)) for key in ("vpn", "proxy", "tor", "relay"))
        raw_type = str(company.get("type") or asn.get("type") or "").lower()
        connection_type = "mobile" if carrier or raw_type == "mobile" else (raw_type or None)

        confidence = 0.35 if coordinate is not None else 0.0
        if connection_type == "mobile" or is_proxy:
            confidence = min(confidence, 0.05)
        elif raw_type == "hosting":
            confidence = min(confidence, 0.10)

        return GeoLocation(
            coordinate=coordinate,
            geo_confidence=confidence,
            connection_type=connection_type,
            is_proxy=is_proxy,
        )

    def resolve(self, ip: str) -> NetworkRange:
        payload = self._lookup(ip)
        asn_data = payload.get("asn") if isinstance(payload.get("asn"), dict) else {}
        asn_value = asn_data.get("asn") or payload.get("asn")
        asn_match = re.search(r"(?:AS)?(\d+)", str(asn_value or ""), re.IGNORECASE)
        route = asn_data.get("route") or payload.get("network")
        if not isinstance(route, str) or not route.strip():
            raise RuntimeError("IPinfo response did not include an ASN network route")

        org = asn_data.get("name") or payload.get("org")
        if isinstance(org, str):
            org = re.sub(r"^AS\d+\s+", "", org.strip(), flags=re.IGNORECASE)

        try:
            return NetworkRange(
                cidr=str(ipaddress.ip_network(route, strict=False)),
                asn=int(asn_match.group(1)) if asn_match else None,
                org=str(org)[:200] if org else None,
                country=str(payload.get("country") or "").upper() or None,
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("IPinfo returned invalid network metadata") from exc

    def _lookup(self, ip: str) -> dict[str, Any]:
        try:
            normalized_ip = str(ipaddress.ip_address(ip))
        except ValueError as exc:
            raise ValueError("ip must be a valid IPv4 or IPv6 address") from exc

        params: dict[str, str] = {}
        token = self._token_provider() if self._token_provider else None
        if token:
            params["token"] = token

        try:
            if self._client is not None:
                response = self._client.get(
                    f"{self.BASE_URL}/{normalized_ip}/json",
                    params=params,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                payload = response.json()
            else:
                with httpx.Client(
                    timeout=self._timeout, follow_redirects=False
                ) as client:
                    response = client.get(
                        f"{self.BASE_URL}/{normalized_ip}/json", params=params
                    )
                    response.raise_for_status()
                    payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("IPinfo lookup failed (%s)", type(exc).__name__)
            raise RuntimeError("IPinfo lookup failed") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("IPinfo returned a non-object response")
        return payload

    @staticmethod
    def _coordinate(payload: dict[str, Any]) -> Coordinate | None:
        raw_location = payload.get("loc")
        if not isinstance(raw_location, str):
            return None
        parts = raw_location.split(",", maxsplit=1)
        if len(parts) != 2:
            return None
        try:
            latitude, longitude = float(parts[0]), float(parts[1])
            accuracy = float(payload.get("accuracy_m", 50000))
            return Coordinate(
                lat=latitude,
                lon=longitude,
                accuracy_m=accuracy,
                source="ipinfo",
            )
        except (TypeError, ValueError):
            return None
