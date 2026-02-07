# -*- coding: utf-8 -*-
"""Keyboard Adapter - pynput implementation for keyboard control"""

import logging
from typing import Optional

from app.application.ports import ActionProvider

logger = logging.getLogger(__name__)


class KeyboardAdapter(ActionProvider):
    """
    Edge adapter for keyboard control using pynput.
    Depends on system keyboard drivers.
    """

    def __init__(self):
        """Initialize keyboard adapter"""
        # Lazy import of pynput to reduce startup memory usage
        try:
            from pynput.keyboard import Controller
            self._pynput_available = True
            self.keyboard = Controller()
        except ImportError:
            logger.warning("pynput.keyboard not available")
            self._pynput_available = False
            self.keyboard = None

    def type_text(self, text: str) -> None:
        """
        Type text using keyboard controller

        Args:
            text: Text to type
        """
        if not self.is_available():
            logger.warning(f"Keyboard not available, would type: {text}")
            return

        try:
            self.keyboard.type(text)
        except Exception as e:
            logger.error(f"Error typing text: {e}")

    def press_key(self, key: str) -> None:
        """
        Press a keyboard key (delegates to AutomationAdapter)

        Args:
            key: Key name to press
        """
        logger.debug("KeyboardAdapter.press_key delegates to AutomationAdapter")

    def press_keys(self, keys: list[str]) -> None:
        """
        Press multiple keys (delegates to AutomationAdapter)

        Args:
            keys: List of key names
        """
        logger.debug("KeyboardAdapter.press_keys delegates to AutomationAdapter")

    def hotkey(self, *keys: str) -> None:
        """
        Press hotkey (delegates to AutomationAdapter)

        Args:
            keys: Keys to press together
        """
        logger.debug("KeyboardAdapter.hotkey delegates to AutomationAdapter")

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """
        Click (delegates to AutomationAdapter)

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button
            clicks: Number of clicks
        """
        logger.debug("KeyboardAdapter.click delegates to AutomationAdapter")

    def locate_on_screen(
        self, image_path: str, timeout: float = None
    ) -> Optional[tuple[int, int]]:
        """
        Locate on screen (delegates to AutomationAdapter)

        Args:
            image_path: Path to image
            timeout: Search timeout

        Returns:
            Coordinates tuple or None
        """
        logger.debug("KeyboardAdapter.locate_on_screen delegates to AutomationAdapter")
        return None

    def is_available(self) -> bool:
        """
        Check if keyboard services are available

        Returns:
            True if keyboard services are available
        """
        return self._pynput_available and self.keyboard is not None
