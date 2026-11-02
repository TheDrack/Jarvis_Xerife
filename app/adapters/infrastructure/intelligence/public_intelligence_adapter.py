"""Read-only adapters for public GDELT, NASA EONET and USGS event feeds.

This adapter is intentionally separate from personal/entity reconnaissance.
External records are untrusted claims and are returned with provenance only.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.application.ports.intelligence_source import IntelligenceSource
from app.core.nexuscomponent import NexusComponent
from app.domain.intelligence.contracts import (
    GeoPoint,
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceEvent,
    SourceHealth,
)

logger = logging.getLogger(__name__)
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
EONET_EVENTS_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"
USGS_ALL_DAY_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)
DEFAULT_GDELT_QUERY = "(technology OR science OR artificial intelligence)"
SOURCE_TERMS = {
    "gdelt": "GDELT data/API terms; original publisher rights remain applicable to each article",
    "nasa_eonet": "NASA EONET API metadata; verify linked source terms before redistribution",
    "usgs_earthquakes": "USGS public earthquake feed; retain attribution and source URL",
}


class PublicIntelligenceAdapter(IntelligenceSource, NexusComponent):
    """Nexus-resolvable, read-only source adapter with injectable HTTP transport."""

    def __init__(
        self, client: Optional[httpx.Client] = None, timeout_seconds: float = 12.0
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("timeout_seconds deve estar entre 0 e 30.")
        self._client = client
        self._timeout = timeout_seconds

    def _get_json(self, url: str, params: Optional[dict] = None) -> Dict[str, Any]:
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, timeout=self._timeout)
            else:
                with httpx.Client(
                    timeout=self._timeout, follow_redirects=False
                ) as client:
                    response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("A fonte retornou JSON fora do contrato esperado.")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Public intelligence source failed (%s)", type(exc).__name__)
            raise RuntimeError(
                "Falha ao consultar fonte pública de inteligência."
            ) from exc

    @staticmethod
    def _event_id(source_id: str, external_id: str) -> str:
        digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:24]
        return f"{source_id}:{digest}"

    @staticmethod
    def _parse_gdelt_time(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None

    @staticmethod
    def _point_from_coordinates(coordinates: Any) -> Optional[GeoPoint]:
        try:
            while (
                isinstance(coordinates, list)
                and coordinates
                and isinstance(coordinates[0], list)
            ):
                coordinates = coordinates[0]
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                return None
            return GeoPoint(
                latitude=float(coordinates[1]), longitude=float(coordinates[0])
            )
        except (TypeError, ValueError):
            return None

    def fetch_gdelt_articles(
        self, query: str = DEFAULT_GDELT_QUERY, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Return bounded global-news records; no article body is scraped or stored."""
        limit = self._validate_limit(limit)
        query = query.strip()
        if not query or len(query) > 300:
            raise ValueError("query deve conter entre 1 e 300 caracteres.")
        payload = self._get_json(
            GDELT_DOC_URL,
            {
                "query": query,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": limit,
                "sort": "HybridRel",
            },
        )
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            raise RuntimeError("GDELT retornou uma lista de artigos inválida.")
        events: List[IntelligenceEvent] = []
        for article in articles[:limit]:
            if not isinstance(article, dict):
                continue
            url, title = article.get("url"), article.get("title")
            if (
                not isinstance(url, str)
                or not url.startswith("https://")
                or not isinstance(title, str)
            ):
                continue
            published_at = self._parse_gdelt_time(article.get("seendate"))
            publisher = article.get("domain") or article.get("sourcecountry")
            events.append(
                IntelligenceEvent(
                    event_id=self._event_id("gdelt", url),
                    source_id="gdelt",
                    domain="global_news",
                    category="news",
                    title=title[:500],
                    url=url,
                    published_at=None,
                    observed_at=published_at or datetime.now(timezone.utc),
                    evidence=IntelligenceEvidence(
                        source_id="gdelt",
                        source_name="GDELT DOC 2.0",
                        url=url,
                        publisher=str(publisher)[:200] if publisher else None,
                        published_at=None,
                        license_or_terms=SOURCE_TERMS["gdelt"],
                    ),
                )
            )
        return [event.model_dump(mode="json") for event in events]

    def fetch_eonet_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return open Earth-observation events with optional GeoJSON locations."""
        limit = self._validate_limit(limit)
        records = self._get_json(
            EONET_EVENTS_URL, {"status": "open", "limit": limit}
        ).get("events", [])
        if not isinstance(records, list):
            raise RuntimeError("NASA EONET retornou uma lista de eventos inválida.")
        events: List[IntelligenceEvent] = []
        for item in records[:limit]:
            if (
                not isinstance(item, dict)
                or not item.get("id")
                or not item.get("title")
            ):
                continue
            geometries = item.get("geometry") or []
            geometry = (
                geometries[-1] if isinstance(geometries, list) and geometries else {}
            )
            point = (
                self._point_from_coordinates(geometry.get("coordinates"))
                if isinstance(geometry, dict)
                else None
            )
            published_at = None
            if isinstance(geometry, dict) and geometry.get("date"):
                try:
                    published_at = datetime.fromisoformat(
                        str(geometry["date"]).replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            sources = item.get("sources") or []
            source_url = next(
                (
                    s.get("url")
                    for s in sources
                    if isinstance(s, dict)
                    and isinstance(s.get("url"), str)
                    and s["url"].startswith("https://")
                ),
                None,
            )
            url = item.get("link") or source_url
            if not isinstance(url, str) or not url.startswith("https://"):
                url = EONET_EVENTS_URL
            categories = item.get("categories") or []
            category = (
                categories[0].get("title", "environment")
                if categories and isinstance(categories[0], dict)
                else "environment"
            )
            events.append(
                IntelligenceEvent(
                    event_id=self._event_id("nasa_eonet", str(item["id"])),
                    source_id="nasa_eonet",
                    domain="climate_disaster",
                    category=str(category)[:100],
                    title=str(item["title"])[:500],
                    summary=str(item.get("description") or "")[:4000] or None,
                    url=url,
                    occurred_at=published_at,
                    location=point,
                    evidence=IntelligenceEvidence(
                        source_id="nasa_eonet",
                        source_name="NASA EONET",
                        url=url,
                        published_at=None,
                        license_or_terms=SOURCE_TERMS["nasa_eonet"],
                    ),
                )
            )
        return [event.model_dump(mode="json") for event in events]

    def fetch_usgs_earthquakes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent USGS earthquake events from the official all-day feed."""
        limit = self._validate_limit(limit)
        features = self._get_json(USGS_ALL_DAY_URL).get("features", [])
        if not isinstance(features, list):
            raise RuntimeError("USGS retornou uma lista de eventos inválida.")
        events: List[IntelligenceEvent] = []
        for feature in features[:limit]:
            if not isinstance(feature, dict) or not feature.get("id"):
                continue
            props, geometry = (
                feature.get("properties") or {},
                feature.get("geometry") or {},
            )
            point = (
                self._point_from_coordinates(geometry.get("coordinates"))
                if isinstance(geometry, dict)
                else None
            )
            timestamp = props.get("time")
            published_at = (
                datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                if isinstance(timestamp, (int, float))
                else None
            )
            url = props.get("url") or USGS_ALL_DAY_URL
            if not isinstance(url, str) or not url.startswith("https://"):
                url = USGS_ALL_DAY_URL
            events.append(
                IntelligenceEvent(
                    event_id=self._event_id("usgs_earthquakes", str(feature["id"])),
                    source_id="usgs_earthquakes",
                    domain="climate_disaster",
                    category="earthquake",
                    title=str(props.get("title") or props.get("place") or "Earthquake")[
                        :500
                    ],
                    url=url,
                    occurred_at=published_at,
                    location=point,
                    magnitude=props.get("mag"),
                    magnitude_unit="magnitude",
                    evidence=IntelligenceEvidence(
                        source_id="usgs_earthquakes",
                        source_name="USGS Earthquake Hazards Program",
                        url=url,
                        published_at=None,
                        license_or_terms=SOURCE_TERMS["usgs_earthquakes"],
                    ),
                )
            )
        return [event.model_dump(mode="json") for event in events]

    def collect_public_events(self, limit: int = 50) -> IntelligenceBatch:
        """Collect independent public sources and report each source's health."""
        self._validate_limit(limit)
        events: List[IntelligenceEvent] = []
        health: List[SourceHealth] = []
        sources = (
            ("gdelt", lambda: self.fetch_gdelt_articles(limit=limit)),
            ("nasa_eonet", lambda: self.fetch_eonet_events(limit=limit)),
            ("usgs_earthquakes", lambda: self.fetch_usgs_earthquakes(limit=limit)),
        )
        for source_id, fetcher in sources:
            try:
                records = fetcher()
                events.extend(
                    IntelligenceEvent.model_validate(item) for item in records
                )
                health.append(SourceHealth(source_id=source_id, available=True))
            except (RuntimeError, ValueError, TypeError) as exc:
                logger.warning("Intelligence source unavailable: %s", source_id)
                health.append(
                    SourceHealth(
                        source_id=source_id,
                        available=False,
                        error_code=type(exc).__name__,
                    )
                )
        return IntelligenceBatch(events=tuple(events), sources=tuple(health))

    def fetch_events(self, limit: int = 50) -> List[IntelligenceEvent]:
        """Port-compatible event collection; inspect collect_public_events for partial failures."""
        return list(self.collect_public_events(limit).events)

    def collect_public_snapshot(self, limit: int = 50) -> Dict[str, Any]:
        """Return a JSON-ready multi-source snapshot with explicit source health."""
        return self.collect_public_events(limit).model_dump(mode="json")

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit deve ser um inteiro entre 1 e 100.")
        return limit

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Expose adapter metadata to Nexus without performing network I/O."""
        return {
            "success": True,
            "adapter_id": "public_intelligence_adapter",
            "execution_mode": "read_only",
            "capabilities": [
                "intelligence.news.search",
                "intelligence.events.environment",
                "intelligence.events.seismic",
                "intelligence.snapshot.read",
            ],
        }

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
