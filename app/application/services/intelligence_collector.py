"""On-demand, provider-neutral collection for Jarvis Universal Intelligence."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.application.services.intelligence_core import IntelligenceCore
from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceReport,
    SourceHealth,
)

logger = logging.getLogger(__name__)


def _configured_gods_eye_adapter():
    entrypoint = os.getenv("JARVIS_GEV_MCP_ENTRYPOINT", "").strip()
    area_names = (
        "JARVIS_GEV_AREA_WEST",
        "JARVIS_GEV_AREA_SOUTH",
        "JARVIS_GEV_AREA_EAST",
        "JARVIS_GEV_AREA_NORTH",
    )
    raw_area = [os.getenv(name, "").strip() for name in area_names]
    if not entrypoint or not all(raw_area):
        return None
    try:
        area = dict(zip(("west", "south", "east", "north"), map(float, raw_area)))
    except ValueError:
        logger.warning("God's Eye area configuration is invalid")
        return None

    from app.adapters.infrastructure.intelligence.gods_eye_mcp_adapter import (
        GodsEyeMcpAdapter,
    )

    return GodsEyeMcpAdapter(area=area, entrypoint=entrypoint)


async def _collect_sync(source: Any, method_name: str, limit: int) -> IntelligenceBatch:
    method = getattr(source, method_name)
    result = await asyncio.to_thread(method, limit)
    return result if isinstance(result, IntelligenceBatch) else IntelligenceBatch.model_validate(result)


async def _collect_gods_eye(source: Any) -> IntelligenceBatch:
    result = await source.collect_observations()
    return result if isinstance(result, IntelligenceBatch) else IntelligenceBatch.model_validate(result)


async def collect_live_intelligence(
    *,
    limit: int = 50,
    public_source: Any | None = None,
    osiris_source: Any | None = None,
    gods_eye_source: Any | None = None,
) -> IntelligenceReport:
    """Collect independent sources concurrently, retaining partial success.

    This operation is on-demand and read-only. It does not write to history,
    schedule recurring collection, or treat candidate correlations as proof.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")

    if public_source is None:
        from app.adapters.infrastructure.intelligence.public_intelligence_adapter import (
            PublicIntelligenceAdapter,
        )
        public_source = PublicIntelligenceAdapter()

    if osiris_source is None:
        from app.adapters.infrastructure.intelligence.osiris_rest_adapter import (
            OsirisRestAdapter,
        )
        osiris_source = OsirisRestAdapter()

    if gods_eye_source is None:
        gods_eye_source = _configured_gods_eye_adapter()

    async def guarded(source_id: str, operation) -> IntelligenceBatch:
        try:
            return await operation()
        except Exception as exc:  # source isolation; details stay in server logs
            logger.warning(
                "Intelligence collection failed for %s (%s)",
                source_id,
                type(exc).__name__,
            )
            error_codes = {
                RuntimeError: "RUNTIME_ERROR",
                TimeoutError: "TIMEOUT",
                ValueError: "INVALID_RESPONSE",
                TypeError: "INVALID_DATA",
            }
            return IntelligenceBatch(
                sources=(
                    SourceHealth(
                        source_id=source_id,
                        available=False,
                        error_code=error_codes.get(type(exc), "SOURCE_ERROR"),
                    ),
                )
            )

    tasks = [
        guarded(
            "public_intelligence",
            lambda: _collect_sync(public_source, "collect_public_events", limit),
        ),
        guarded(
            "osiris",
            lambda: _collect_sync(osiris_source, "collect_events", limit),
        ),
    ]
    if gods_eye_source is None:
        tasks.append(
            asyncio.sleep(
                0,
                result=IntelligenceBatch(
                    sources=(
                        SourceHealth(
                            source_id="gods_eye_view",
                            available=False,
                            error_code="NOT_CONFIGURED",
                        ),
                    )
                ),
            )
        )
    else:
        tasks.append(guarded("gods_eye_view", lambda: _collect_gods_eye(gods_eye_source)))

    batches = await asyncio.gather(*tasks)
    merged = IntelligenceBatch(
        events=tuple(event for batch in batches for event in batch.events),
        observations=tuple(
            observation for batch in batches for observation in batch.observations
        ),
        sources=tuple(source for batch in batches for source in batch.sources),
    )
    return IntelligenceCore().process(merged)

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]