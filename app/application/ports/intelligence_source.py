"""Port for public, non-person-targeted intelligence sources."""

from abc import ABC, abstractmethod
from typing import List

from app.domain.intelligence.contracts import IntelligenceEvent


class IntelligenceSource(ABC):
    """A source adapter returns normalized events with source provenance."""

    @abstractmethod
    def fetch_events(self, limit: int = 50) -> List[IntelligenceEvent]:
        """Fetch a bounded batch of public events; never perform interventions."""
