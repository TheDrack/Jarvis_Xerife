"""Port for read-only providers that report time-stamped entity observations."""

from abc import ABC, abstractmethod

from app.domain.intelligence.contracts import IntelligenceBatch


class IntelligenceObservationSource(ABC):
    """An observation source returns bounded snapshots with source provenance."""

    @abstractmethod
    async def collect_observations(self) -> IntelligenceBatch:
        """Collect a bounded batch; implementations must not perform actions."""
