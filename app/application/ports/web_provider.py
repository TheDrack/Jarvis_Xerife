from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Web Provider Port - Interface for web navigation"""

from abc import ABC, abstractmethod


class WebProvider(NexusComponent, ABC):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """
    Port (interface) for web navigation and browser automation.
    Adapters must implement this interface.
    """

    @abstractmethod
    def open_url(self, url: str) -> None:
        """
        Open URL in browser

        Args:
            url: URL to open
        """
        pass

    @abstractmethod
    def search_on_page(self, search_text: str) -> None:
        """
        Search for text on current page

        Args:
            search_text: Text to search for
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if web services are available

        Returns:
            True if web services are available
        """
        pass
