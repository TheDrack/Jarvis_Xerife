"""Read-only God's Eye View MCP adapter for bounded entity observations."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlsplit

from app.application.ports.intelligence_observation_source import IntelligenceObservationSource
from app.domain.intelligence.contracts import (
    GeoPoint,
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceObservation,
    SourceHealth,
)

logger = logging.getLogger(__name__)

SOURCE_ID = "gods_eye_view"
SOURCE_NAME = "God's Eye View MCP"
SOURCE_REPOSITORY = "https://github.com/bilawalsidhu/gods-eye-view"
SOURCE_TERMS = (
    "God's Eye View MCP observation; upstream provider attribution and "
    "underlying dataset license/terms apply independently."
)

# The allowlist is intentionally narrower than the upstream MCP catalog.
_QUERY_SPECS = {
    "aircraft_in_area": ("aircraft", "area", "id", "last_contact"),
    "vessels_in_area": ("vessel", "area", "mmsi", "observed_at"),
    "satellites_overhead": ("satellite", "location", "norad", None),
}
_ATTRIBUTE_KEYS = {
    "aircraft": (
        "callsign", "altitude_m", "on_ground", "speed_mps", "course_deg",
        "vertical_rate_mps", "type_code", "registration", "operator",
        "origin_country", "distance_km",
    ),
    "vessel": (
        "name", "imo", "type", "destination", "speed_mps", "course_deg",
        "heading_deg", "distance_km",
    ),
    "satellite": ("name", "elevation_deg", "azimuth_deg", "direction"),
}


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _structured_payload(result: Any) -> dict[str, Any]:
    payload = _field(result, "structuredContent")
    if payload is None:
        payload = _field(result, "structured_content")
    if isinstance(payload, dict):
        return payload
    content = _field(result, "content", [])
    for item in content or []:
        text = _field(item, "text")
        if isinstance(text, str):
            try:
                import json
                decoded = json.loads(text)
            except (TypeError, ValueError):
                continue
            if isinstance(decoded, dict):
                return decoded
    raise ValueError("MCP tool returned no structured object")


def _safe_attributes(entity_type: str, row: dict[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for key in _ATTRIBUTE_KEYS[entity_type]:
        value = row.get(key)
        if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
            attributes[key] = value[:1000] if isinstance(value, str) else value
        elif isinstance(value, float) and math.isfinite(value):
            attributes[key] = value
    return attributes


class GodsEyeMcpAdapter(IntelligenceObservationSource):
    """Collect bounded aircraft, vessel and satellite snapshots from local GEV."""

    def __init__(
        self,
        *,
        area: dict[str, float],
        entrypoint: str | Path | None = None,
        api_base: str = "http://127.0.0.1:4173",
        limit: int = 50,
        timeout_seconds: float = 20.0,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._area = self._validate_area(area)
        self._location = {
            "lat": (self._area["south"] + self._area["north"]) / 2,
            "lon": (self._area["west"] + self._area["east"]) / 2,
        }
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        if not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be greater than 0 and at most 60")
        self._limit = limit
        self._timeout = timeout_seconds
        configured_entrypoint = entrypoint or os.getenv("JARVIS_GEV_MCP_ENTRYPOINT")
        self._entrypoint = Path(configured_entrypoint).expanduser() if configured_entrypoint else None
        self._api_base = self._validate_api_base(api_base)
        self._session_factory = session_factory

    @staticmethod
    def _validate_area(area: dict[str, float]) -> dict[str, float]:
        if not isinstance(area, dict) or set(area) != {"west", "south", "east", "north"}:
            raise ValueError("area must contain exactly west, south, east and north")
        try:
            values = {key: float(value) for key, value in area.items()}
        except (TypeError, ValueError) as exc:
            raise ValueError("area coordinates must be numeric") from exc
        west, south, east, north = (
            values["west"], values["south"], values["east"], values["north"]
        )
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("area coordinates must be finite")
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("area coordinates are outside geographic bounds")
        if east - west > 10 or north - south > 10:
            raise ValueError("area must not exceed 10 degrees on either side")
        return values

    @staticmethod
    def _validate_api_base(value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("api_base must be a loopback HTTP(S) origin without path or credentials")
        return value.rstrip("/")

    @asynccontextmanager
    async def _open_session(self) -> AsyncIterator[Any]:
        if self._session_factory is not None:
            async with self._session_factory() as session:
                yield session
            return

        if self._entrypoint is None:
            raise RuntimeError("JARVIS_GEV_MCP_ENTRYPOINT is not configured")
        if not self._entrypoint.is_absolute() or not self._entrypoint.is_file():
            raise RuntimeError("configured GEV MCP entrypoint must be an existing absolute file")

        # Import the optional Edge dependency only when this adapter is used.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        script = self._entrypoint.resolve()
        server = StdioServerParameters(
            command="node",
            args=[str(script), "--api-base", self._api_base],
            cwd=str(script.parents[2]),
        )
        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=self._timeout)
                yield session

    def _tool_arguments(self, tool_name: str) -> dict[str, Any]:
        if tool_name in {"aircraft_in_area", "vessels_in_area"}:
            return {
                "area": {
                    "bbox": [
                        self._area["west"],
                        self._area["south"],
                        self._area["east"],
                        self._area["north"],
                    ]
                },
                "limit": self._limit,
            }
        return {"location": dict(self._location), "limit": self._limit}

    @staticmethod
    def _is_safe_query_tool(definition: Any, required_property: str) -> bool:
        annotations = _field(definition, "annotations", {}) or {}
        read_only_hint = _field(annotations, "readOnlyHint")
        if read_only_hint is None:
            # MCP SDK model objects expose snake_case attributes, while JSON
            # wire dictionaries use camelCase annotation keys.
            read_only_hint = _field(annotations, "read_only_hint", False)
        destructive_hint = _field(annotations, "destructiveHint")
        if destructive_hint is None:
            destructive_hint = _field(annotations, "destructive_hint", False)
        if read_only_hint is not True:
            return False
        if destructive_hint is True:
            return False
        schema = _field(definition, "inputSchema", None)
        if schema is None:
            schema = _field(definition, "input_schema", None)
        if not isinstance(schema, dict) or schema.get("type") != "object":
            return False
        properties = schema.get("properties")
        required = schema.get("required", [])
        return (
            isinstance(properties, dict)
            and required_property in properties
            and required_property in required
        )

    def _to_observation(
        self,
        entity_type: str,
        row: Any,
        data: dict[str, Any],
        timestamp_field: str | None,
    ) -> IntelligenceObservation | None:
        if not isinstance(row, dict):
            return None
        identity_field = {
            "aircraft": "id", "vessel": "mmsi", "satellite": "norad"
        }[entity_type]
        entity_id = row.get(identity_field)
        if entity_id is None or not str(entity_id).strip():
            return None

        observed_at = _parse_timestamp(
            row.get(timestamp_field) if timestamp_field else data.get("at")
        )
        if observed_at is None and entity_type == "aircraft":
            observed_at = _parse_timestamp(data.get("observed_at"))
        if observed_at is None:
            return None

        latitude, longitude = row.get("lat"), row.get("lon")
        position = None
        if latitude is not None and longitude is not None:
            try:
                position = GeoPoint(latitude=float(latitude), longitude=float(longitude))
            except (TypeError, ValueError):
                return None

        identity = f"{SOURCE_ID}\0{entity_type}\0{entity_id}\0{observed_at.isoformat()}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        attribution = data.get("attribution") or data.get("source") or "not supplied"
        evidence = IntelligenceEvidence(
            source_id=SOURCE_ID,
            source_name=SOURCE_NAME,
            url=SOURCE_REPOSITORY,
            publisher=str(data.get("source") or SOURCE_NAME)[:200],
            collected_at=datetime.now(timezone.utc),
            license_or_terms=(
                f"{SOURCE_TERMS} Attribution reported by provider: {str(attribution)[:250]}"
            ),
        )
        return IntelligenceObservation(
            observation_id=f"{SOURCE_ID}:{entity_type}:{digest}",
            source_id=SOURCE_ID,
            entity_type=entity_type,
            entity_id=str(entity_id)[:160],
            observed_at=observed_at,
            position=position,
            attributes=_safe_attributes(entity_type, row),
            evidence=(evidence,),
        )

    async def collect_observations(self) -> IntelligenceBatch:
        """Discover and invoke only safe allowlisted query tools, returning partial health."""
        observations: list[IntelligenceObservation] = []
        succeeded = 0
        failed = 0
        try:
            async with self._open_session() as session:
                listing = await asyncio.wait_for(session.list_tools(), timeout=self._timeout)
                definitions = {
                    _field(tool, "name"): tool
                    for tool in (_field(listing, "tools", []) or [])
                    if isinstance(_field(tool, "name"), str)
                }
                for tool_name, (entity_type, required_property, _, timestamp_field) in _QUERY_SPECS.items():
                    definition = definitions.get(tool_name)
                    if definition is None or not self._is_safe_query_tool(definition, required_property):
                        continue
                    try:
                        result = await asyncio.wait_for(
                            session.call_tool(tool_name, arguments=self._tool_arguments(tool_name)),
                            timeout=self._timeout,
                        )
                        if _field(result, "isError", False):
                            raise RuntimeError("MCP query returned an error")
                        data = _structured_payload(result)
                        rows = data.get("rows", [])
                        if not isinstance(rows, list):
                            raise ValueError("MCP query rows are malformed")
                        for row in rows[: self._limit]:
                            observation = self._to_observation(
                                entity_type, row, data, timestamp_field
                            )
                            if observation is not None:
                                observations.append(observation)
                        succeeded += 1
                    except (asyncio.TimeoutError, RuntimeError, ValueError, TypeError):
                        failed += 1
                        logger.warning("God's Eye View query failed: %s", tool_name)

            available = succeeded > 0
            error_code = (
                "PartialFailure" if available and failed else
                "NoReadOnlyTools" if not succeeded and not failed else
                "SourceUnavailable" if not succeeded else
                None
            )
            return IntelligenceBatch(
                observations=tuple(observations),
                sources=(
                    SourceHealth(
                        source_id=SOURCE_ID,
                        available=available,
                        error_code=error_code,
                    ),
                ),
            )
        except Exception as exc:
            logger.warning("God's Eye View MCP source unavailable (%s)", type(exc).__name__)
            return IntelligenceBatch(
                sources=(
                    SourceHealth(
                        source_id=SOURCE_ID,
                        available=False,
                        error_code=type(exc).__name__,
                    ),
                )
            )

    def execute(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Expose adapter metadata without starting a process or querying GEV."""
        return {
            "success": True,
            "adapter_id": "gods_eye_mcp_adapter",
            "execution_mode": "read_only",
            "configured": self._session_factory is not None or self._entrypoint is not None,
            "capabilities": [
                "intelligence.observations.aircraft",
                "intelligence.observations.vessels",
                "intelligence.observations.satellites",
            ],
        }
