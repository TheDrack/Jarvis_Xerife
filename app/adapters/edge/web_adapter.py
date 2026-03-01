from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Web Adapter - Browser automation implementation"""

import logging
import webbrowser

from app.application.ports import ActionProvider, WebProvider

logger = logging.getLogger(__name__)


class WebAdapter(WebProvider):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Adapter for web navigation using standard webbrowser module.
    Requires ActionProvider for page interaction.
    """

    def __init__(self, action_provider: ActionProvider):
        """
        Initialize web adapter

        Args:
            action_provider: Adapter for keyboard/mouse actions
        """
        self.action = action_provider

    def open_url(self, url: str) -> None:
        """
        Open URL in default browser

        Args:
            url: URL to open
        """
        try:
            webbrowser.open(url)
            logger.info(f"Opened URL: {url}")
        except Exception as e:
            logger.error(f"Error opening URL: {e}")

    def search_on_page(self, search_text: str) -> None:
        """
        Search for text on current page using Ctrl+F

        Args:
            search_text: Text to search for
        """
        try:
            self.action.hotkey("ctrl", "f")
            self.action.type_text(search_text)
            logger.info(f"Searched for: {search_text}")
        except Exception as e:
            logger.error(f"Error searching on page: {e}")

    def is_available(self) -> bool:
        """
        Check if web services are available

        Returns:
            True (webbrowser is always available)
        """
        return True
