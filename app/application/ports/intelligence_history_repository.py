"""Application port for durable, append-only intelligence history."""

from __future__ import annotations

from typing import Protocol

from app.domain.intelligence.contracts import IntelligenceReport


class IntelligenceHistoryRepository(Protocol):
    """Persist normalized intelligence events and observations."""

    def persist(self, report: IntelligenceReport) -> None:
        """Append a report idempotently; never update or delete prior snapshots."""
