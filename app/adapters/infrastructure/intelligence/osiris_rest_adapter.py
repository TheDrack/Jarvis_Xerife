"""Read-only OSIRIS REST adapter for bounded public event feeds."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from app.application.ports.intelligence_source import IntelligenceSource
from app.core.nexuscomponent import NexusComponent
from app.domain.intelligence.contracts import (
    GeoPoint,
    IntelligenceBatch,
    IntelligenceEvent,
    IntelligenceEvidence,
    SourceHealth,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "OSIRIS Dashboard"
SOURCE_REPOSITORY = "https://github.com/Pendia/OSIRIS-Dashboard-OSINT"
_ROUTE_SPECS = {
    "earthquakes": ("earthquakes", "osiris_earthquakes"),
    "fires": ("fires", "osiris_fires"),
    "news": ("news", "osiris_news"),
    "weather": ("weather", "osiris_weather"),
}
_SOURCE_TERMS = {
    "usgs_earthquakes": (
        "OSIRIS aggregation of USGS earthquake GeoJSON; preserve USGS event-page "
        "attribution and original USGS data terms."
    ),
    "nasa_firms": (
        "OSIRIS aggregation of NASA FIRMS active-fire observations; underlying "
        "dataset attribution and terms apply independently."
    ),
    "nasa_eonet": (
        "OSIRIS aggregation of NASA EONET open natural-event metadata; underlying "
        "dataset attribution and terms apply independently."
    ),
    "osiris_news": (
        "OSIRIS public news/OSINT feed; original publisher/channel rights and "
        "source bias apply. Feed classification is not independent verification."
    ),
    "noaa_nws": (
        "OSIRIS aggregation of NOAA/NWS active alerts; preserve alert-specific "
        "source links and NOAA data attribution."
    ),
    "gdacs": (
        "OSIRIS aggregation of GDACS disaster alerts; preserve GDACS source links "
        "and the original provider terms."
    ),
}
_USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
)
_FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/active_fire/"
_EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
_WEATHER_PROVIDERS = {
    "NASA EONET": ("nasa_eonet", _EONET_URL),
    "NOAA/NWS": ("noaa_nws", "https://api.weather.gov/alerts/active"),
    "GDACS": ("gdacs", "https://www.gdacs.org/"),
}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _https_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value


def _digest(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


class OsirisRestAdapter(IntelligenceSource, NexusComponent):
    """Collect bounded public events from fixed OSIRIS REST routes."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 4_000_000,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than 0 and at most 30")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1024 <= max_response_bytes <= 20_000_000
        ):
            raise ValueError("max_response_bytes must be between 1024 and 20000000")
        configured = base_url or os.getenv("JARVIS_OSIRIS_API_BASE_URL")
        self._base_url = self._validate_base_url(configured) if configured else None
        self._client = client
        self._client_factory = client_factory
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes

    @staticmethod
    def _validate_base_url(value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must be an HTTPS origin without credentials, path, query or fragment"
            )
        if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("OSIRIS base_url must not target loopback")
        return value.rstrip("/")

    def _read_response(self, client: httpx.Client, url: str) -> dict[str, Any]:
        body = bytearray()
        with client.stream(
            "GET",
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Jarvis-Universal-Intelligence/0.1",
            },
            timeout=self._timeout,
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self._max_response_bytes:
                    raise ValueError("OSIRIS response exceeds configured byte limit")

        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("OSIRIS route returned a non-object JSON payload")
        if payload.get("error"):
            raise RuntimeError("OSIRIS route reported an upstream error")
        return payload

    def _get_json(self, route: str) -> dict[str, Any]:
        if route not in _ROUTE_SPECS:
            raise ValueError("OSIRIS route is not allowlisted")
        if self._base_url is None:
            raise RuntimeError("JARVIS_OSIRIS_API_BASE_URL is not configured")
        url = f"{self._base_url}/api/{route}"

        if self._client is not None:
            return self._read_response(self._client, url)
        with self._client_factory(
            timeout=self._timeout,
            follow_redirects=False,
        ) as client:
            return self._read_response(client, url)

    @staticmethod
    def _evidence(
        *,
        source_id: str,
        source_name: str,
        url: str,
        publisher: str | None,
        published_at: datetime | None,
    ) -> IntelligenceEvidence:
        return IntelligenceEvidence(
            source_id=source_id,
            source_name=source_name,
            url=url,
            publisher=publisher[:200] if publisher else None,
            published_at=published_at,
            collected_at=datetime.now(timezone.utc),
            license_or_terms=_SOURCE_TERMS[source_id],
        )

    def _parse_earthquakes(
        self, payload: dict[str, Any], limit: int
    ) -> list[IntelligenceEvent]:
        records = payload.get("earthquakes")
        if not isinstance(records, list):
            raise ValueError("OSIRIS earthquakes collection is malformed")
        observed_at = _parse_datetime(payload.get("timestamp")) or datetime.now(timezone.utc)
        events: list[IntelligenceEvent] = []

        for row in records[:limit]:
            if not isinstance(row, dict):
                continue
            external_id = row.get("id")
            occurred_at = _parse_datetime(row.get("time"))
            latitude = _finite_number(row.get("lat"))
            longitude = _finite_number(row.get("lng"))
            if (
                not isinstance(external_id, (str, int))
                or not str(external_id).strip()
                or occurred_at is None
                or latitude is None
                or longitude is None
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                continue

            url = _https_url(row.get("url")) or _USGS_FEED_URL
            magnitude = _finite_number(row.get("magnitude"))
            place = str(row.get("place") or "Unspecified location")[:300]
            title = (
                f"Earthquake M{magnitude:g} — {place}"
                if magnitude is not None
                else f"Earthquake — {place}"
            )
            details = []
            depth = _finite_number(row.get("depth"))
            if depth is not None:
                details.append(f"depth_km={depth:g}")
            if isinstance(row.get("tsunami"), (bool, int)):
                details.append(f"tsunami={bool(row['tsunami'])}")
            if row.get("alert") is not None:
                details.append(f"alert={str(row['alert'])[:40]}")
            if row.get("felt") is not None:
                details.append(f"felt={str(row['felt'])[:40]}")

            source_id = "usgs_earthquakes"
            evidence = self._evidence(
                source_id=source_id,
                source_name="USGS Earthquake Hazards Program (via OSIRIS)",
                url=url,
                publisher="USGS",
                published_at=occurred_at,
            )
            events.append(
                IntelligenceEvent(
                    event_id=f"{source_id}:{_digest(str(external_id))}",
                    source_id=source_id,
                    domain="climate_disaster",
                    category="earthquake",
                    title=title[:500],
                    summary="; ".join(details) or None,
                    url=url,
                    occurred_at=occurred_at,
                    observed_at=observed_at,
                    location=GeoPoint(latitude=latitude, longitude=longitude),
                    magnitude=magnitude,
                    magnitude_unit="magnitude" if magnitude is not None else None,
                    evidence=evidence,
                )
            )
        return events

    def _parse_fires(
        self, payload: dict[str, Any], limit: int
    ) -> list[IntelligenceEvent]:
        records = payload.get("fires")
        if not isinstance(records, list):
            raise ValueError("OSIRIS fires collection is malformed")
        observed_at = _parse_datetime(payload.get("timestamp")) or datetime.now(timezone.utc)
        route_source = str(payload.get("source") or "Unknown")[:120]
        events: list[IntelligenceEvent] = []

        for row in records[:limit]:
            if not isinstance(row, dict):
                continue
            latitude = _finite_number(row.get("lat"))
            longitude = _finite_number(row.get("lng"))
            if (
                latitude is None
                or longitude is None
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                continue

            event_type = str(row.get("type") or "fire").lower()[:40]
            date_text = str(row.get("date") or "")[:20]
            time_text = str(row.get("time") or "")[:8]
            occurred_at = None
            if date_text and time_text.isdigit() and 1 <= len(time_text) <= 4:
                padded = time_text.zfill(4)
                occurred_at = _parse_datetime(
                    f"{date_text}T{padded[:2]}:{padded[2:]}:00Z"
                )

            is_volcano = (
                event_type == "volcano"
                or str(row.get("title", "")).startswith("[VOLCANO]")
            )
            source_id = "nasa_eonet" if is_volcano else "nasa_firms"
            publisher = "NASA EONET" if is_volcano else "NASA FIRMS"
            evidence_url = _EONET_URL if publisher == "NASA EONET" else _FIRMS_URL
            identity = _digest(
                publisher,
                event_type,
                f"{latitude:.3f}",
                f"{longitude:.3f}",
                date_text,
                time_text,
                str(row.get("title") or ""),
            )
            title = str(
                row.get("title")
                or ("Volcanic activity" if is_volcano else "Active fire detection")
            )[:500]

            details = []
            for key in ("brightness", "confidence", "frp"):
                value = row.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    details.append(f"{key}={str(value)[:80]}")
            if route_source != "Unknown":
                details.append(f"OSIRIS feed source={route_source}")

            evidence = self._evidence(
                source_id=source_id,
                source_name=f"{publisher} (via OSIRIS)",
                url=evidence_url,
                publisher=publisher,
                published_at=occurred_at,
            )
            events.append(
                IntelligenceEvent(
                    event_id=f"{source_id}:{identity}",
                    source_id=source_id,
                    domain="climate_disaster",
                    category="volcano" if is_volcano else "wildfire",
                    title=title,
                    summary="; ".join(details) or None,
                    url=evidence_url,
                    occurred_at=occurred_at,
                    observed_at=observed_at,
                    location=GeoPoint(latitude=latitude, longitude=longitude),
                    evidence=evidence,
                )
            )
        return events

    def _parse_news(
        self, payload: dict[str, Any], limit: int
    ) -> list[IntelligenceEvent]:
        records = payload.get("news")
        if not isinstance(records, list):
            raise ValueError("OSIRIS news collection is malformed")
        observed_at = _parse_datetime(payload.get("timestamp")) or datetime.now(timezone.utc)
        events: list[IntelligenceEvent] = []

        for row in records[:limit]:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            url = _https_url(row.get("link"))
            published_at = _parse_datetime(row.get("published"))
            external_id = row.get("id")
            if (
                not isinstance(title, str)
                or not title.strip()
                or url is None
                or published_at is None
                or not isinstance(external_id, (str, int))
                or not str(external_id).strip()
            ):
                continue

            publisher = str(
                row.get("source_name") or row.get("source") or "Unknown source"
            )[:200]
            alert_kind = str(row.get("alert_kind") or "news")[:100]
            summary = row.get("summary") or row.get("description")
            if not isinstance(summary, str):
                summary = None
            else:
                summary = summary[:4000]

            # OSIRIS keyword-derived country anchors are not event geolocation.
            evidence = self._evidence(
                source_id="osiris_news",
                source_name=f"{SOURCE_NAME} public news feed",
                url=url,
                publisher=publisher,
                published_at=published_at,
            )
            events.append(
                IntelligenceEvent(
                    event_id=f"osiris_news:{_digest(str(external_id))}",
                    source_id="osiris_news",
                    domain="global_news",
                    category=alert_kind,
                    title=title.strip()[:500],
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    observed_at=observed_at,
                    location=None,
                    evidence=evidence,
                )
            )
        return events

    def _parse_weather(
        self, payload: dict[str, Any], limit: int
    ) -> list[IntelligenceEvent]:
        records = payload.get("events")
        if not isinstance(records, list):
            raise ValueError("OSIRIS weather collection is malformed")
        observed_at = _parse_datetime(payload.get("timestamp")) or datetime.now(timezone.utc)
        events: list[IntelligenceEvent] = []

        for row in records[:limit]:
            if not isinstance(row, dict):
                continue
            external_id = row.get("id")
            title = row.get("title")
            provider = row.get("provider")
            provider_spec = _WEATHER_PROVIDERS.get(provider) if isinstance(provider, str) else None
            if (
                not isinstance(external_id, (str, int))
                or not str(external_id).strip()
                or not isinstance(title, str)
                or not title.strip()
                or provider_spec is None
            ):
                continue

            source_id, fallback_url = provider_spec
            url = _https_url(row.get("source")) or fallback_url
            category = str(row.get("category") or row.get("type") or "weather_alert")[:100]
            details: list[str] = []
            for key in ("type", "severity", "area", "date", "expires"):
                value = row.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    details.append(f"{key}={str(value)[:300]}")

            position = None
            if provider != "NOAA/NWS":
                latitude = _finite_number(row.get("lat"))
                longitude = _finite_number(row.get("lng"))
                if (
                    latitude is None
                    or longitude is None
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    continue
                # EONET rows are emitted only for Point geometry; GDACS rows
                # carry explicit geo:lat/geo:long coordinates in the RSS item.
                position = GeoPoint(latitude=latitude, longitude=longitude)

            # OSIRIS reduces NOAA polygon geometry to a representative marker
            # without exposing the original geometry type, so NWS gets no point.
            evidence = self._evidence(
                source_id=source_id,
                source_name=f"{provider} (via OSIRIS)",
                url=url,
                publisher=provider,
                published_at=None,
            )
            events.append(
                IntelligenceEvent(
                    event_id=f"{source_id}:{_digest(str(external_id))}",
                    source_id=source_id,
                    domain="climate_disaster",
                    category=category,
                    title=title.strip()[:500],
                    summary="; ".join(details)[:4000] or None,
                    url=url,
                    observed_at=observed_at,
                    location=position,
                    evidence=evidence,
                )
            )
        return events

    def collect_events(self, limit: int = 50) -> IntelligenceBatch:
        """Collect fixed event routes independently, preserving partial successes."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be an integer between 1 and 100")

        if self._base_url is None:
            return IntelligenceBatch(
                sources=tuple(
                    SourceHealth(
                        source_id=source_id,
                        available=False,
                        error_code="NotConfigured",
                    )
                    for _, source_id in _ROUTE_SPECS.values()
                )
            )

        parsers = {
            "earthquakes": self._parse_earthquakes,
            "fires": self._parse_fires,
            "news": self._parse_news,
            "weather": self._parse_weather,
        }
        events: list[IntelligenceEvent] = []
        health: list[SourceHealth] = []
        for route, source_id in _ROUTE_SPECS.values():
            try:
                payload = self._get_json(route)
                events.extend(parsers[route](payload, limit))
                health.append(SourceHealth(source_id=source_id, available=True))
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                logger.warning(
                    "OSIRIS route unavailable: %s (%s)", route, type(exc).__name__
                )
                health.append(
                    SourceHealth(
                        source_id=source_id,
                        available=False,
                        error_code=type(exc).__name__,
                    )
                )
        return IntelligenceBatch(events=tuple(events), sources=tuple(health))

    def fetch_events(self, limit: int = 50) -> list[IntelligenceEvent]:
        """Port-compatible collection; use collect_events for route health."""
        return list(self.collect_events(limit).events)

    def collect_public_snapshot(self, limit: int = 50) -> dict[str, Any]:
        """Return a JSON-ready OSIRIS snapshot with route-level health."""
        return self.collect_events(limit).model_dump(mode="json")

    def execute(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Expose metadata to Nexus without performing network I/O."""
        return {
            "success": True,
            "adapter_id": "osiris_rest_adapter",
            "execution_mode": "read_only",
            "configured": self._base_url is not None,
            "capabilities": [
                "intelligence.events.seismic",
                "intelligence.events.wildfire",
                "intelligence.news.read",
                "intelligence.events.weather",
            ],
        }

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
