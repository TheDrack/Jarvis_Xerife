"""Port for durable persistence of user-partitioned semantic-memory events."""

from typing import Any, Dict, List, Optional, Protocol


class VectorMemoryStore(Protocol):
    """Storage contract used by VectorMemoryAdapter.

    `user_id=None` always means the system partition, never all users.
    Global deletion is a separate explicit operation.
    """

    @property
    def is_available(self) -> bool:
        """Whether a configured persistence client exists."""
        ...

    def is_healthy(self) -> bool:
        """Return whether the persistence backend is reachable."""
        ...

    def append(
        self,
        event: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> None:
        """Append one sanitized event under the trusted user partition."""
        ...

    def list_events(
        self,
        user_id: Optional[str] = None,
        days_back: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read only the requested user partition; None selects system memory."""
        ...

    def delete_events(self, user_id: Optional[str] = None) -> None:
        """Delete only the requested partition; None selects system memory."""
        ...

    def delete_all(self) -> None:
        """Explicitly delete all partitions."""
        ...
