# -*- coding: utf-8 -*-
"""Memory Provider Port - Interface for vector/semantic memory persistence"""

from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent


class MemoryProvider(NexusComponent):
    """
    Port (interface) for biographical / vector memory.

    Adapters must implement this interface to enable semantic memory storage
    and retrieval for the JARVIS assistant.
    """

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execução automática JARVIS."""
        return {"success": False, "not_implemented": True}

    @abstractmethod
    def store_event(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Encode *text* as a vector and persist it with optional metadata.

        Args:
            text: The raw text to store (user command or LLM response).
            metadata: Arbitrary key/value metadata attached to the event.
            timestamp: Timestamp of the event (defaults to now).

        Returns:
            The unique identifier assigned to the stored event.
        """
        pass

    @abstractmethod
    def query_similar(
        self,
        query_text: str,
        top_k: int = 5,
        days_back: Optional[int] = 30,
    ) -> List[Dict[str, Any]]:
        """
        Return the *top_k* most semantically similar stored events.

        Args:
            query_text: The text used as the similarity query.
            top_k: Maximum number of results to return.
            days_back: If set, restricts results to events within the last N days.

        Returns:
            A list of dicts, each containing at least ``text``, ``score``, and
            ``metadata`` keys.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored events from the memory store."""
        pass
