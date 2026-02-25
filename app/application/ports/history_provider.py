from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""History Provider Port - Interface for command history persistence"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


class HistoryProvider(NexusComponent, ABC):
    """
    Port (interface) for command history persistence.
    Adapters must implement this interface.
    """

    @abstractmethod
    def save_interaction(
        self,
        user_input: str,
        command_type: str,
        parameters: Dict[str, Any],
        success: bool,
        response_text: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Save a command interaction to the history

        Args:
            user_input: Raw user input
            command_type: Type of command executed
            parameters: Command parameters as dict
            success: Whether command succeeded
            response_text: Response message
            timestamp: Timestamp of the interaction (defaults to now)
        """
        pass

    @abstractmethod
    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent command history

        Args:
            limit: Maximum number of commands to return

        Returns:
            List of command history items
        """
        pass

    @abstractmethod
    def get_most_frequent_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most frequently used commands using SQL aggregation

        Args:
            limit: Maximum number of commands to return

        Returns:
            List of command types with their frequency counts
        """
        pass

    @abstractmethod
    def clear_history(self) -> None:
        """Clear all command history"""
        pass
