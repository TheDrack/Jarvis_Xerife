# -*- coding: utf-8 -*-
"""System Controller Port - Generic interface for system control"""

from abc import ABC, abstractmethod
from typing import Optional


class SystemController(ABC):
    """
    Port (interface) for generic system control operations.
    Adapters must implement this interface.
    """

    @abstractmethod
    def execute_command(self, command: str, params: Optional[dict] = None) -> bool:
        """
        Execute a generic system command

        Args:
            command: Command identifier
            params: Optional parameters

        Returns:
            True if command executed successfully
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if system control is available

        Returns:
            True if system control is available
        """
        pass
