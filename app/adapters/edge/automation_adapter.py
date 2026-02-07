# -*- coding: utf-8 -*-
"""Automation Adapter - PyAutoGUI implementation for screen automation"""

import logging
import time
from typing import Optional

from app.application.ports import ActionProvider

logger = logging.getLogger(__name__)


class AutomationAdapter(ActionProvider):
    """
    Edge adapter for system automation using PyAutoGUI.
    Depends on display server (X11, Wayland, etc.).
    """

    def __init__(self, pause: float = 0.4, search_timeout: float = 7.5):
        """
        Initialize automation adapter

        Args:
            pause: Pause duration between actions
            search_timeout: Timeout for image search operations
        """
        self.pause = pause
        self.search_timeout = search_timeout

        # Lazy import of pyautogui to reduce startup memory usage
        try:
            import pyautogui
            self._pyautogui = pyautogui
            self._pyautogui_available = True
            pyautogui.PAUSE = pause
        except ImportError:
            self._pyautogui = None
            self._pyautogui_available = False

    def type_text(self, text: str) -> None:
        """
        Type text using PyAutoGUI (not keyboard controller)

        Args:
            text: Text to type
        """
        if not self.is_available():
            logger.warning(f"PyAutoGUI not available, would type: {text}")
            return

        try:
            self._pyautogui.write(text)
        except Exception as e:
            logger.error(f"Error typing text: {e}")

    def press_key(self, key: str) -> None:
        """
        Press a keyboard key

        Args:
            key: Key name to press
        """
        if not self.is_available():
            logger.warning(f"PyAutoGUI not available, would press: {key}")
            return

        try:
            self._pyautogui.press(key)
        except Exception as e:
            logger.error(f"Error pressing key: {e}")

    def press_keys(self, keys: list[str]) -> None:
        """
        Press multiple keys sequentially

        Args:
            keys: List of key names to press
        """
        for key in keys:
            self.press_key(key)

    def hotkey(self, *keys: str) -> None:
        """
        Press a hotkey combination

        Args:
            keys: Keys to press together
        """
        if not self.is_available():
            logger.warning(f"PyAutoGUI not available, would press hotkey: {keys}")
            return

        try:
            self._pyautogui.hotkey(*keys)
        except Exception as e:
            logger.error(f"Error pressing hotkey: {e}")

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """
        Click at specific coordinates

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
            clicks: Number of clicks
        """
        if not self.is_available():
            logger.warning(f"PyAutoGUI not available, would click at ({x}, {y})")
            return

        try:
            self._pyautogui.click(x, y, button=button, clicks=clicks)
        except Exception as e:
            logger.error(f"Error clicking: {e}")

    def locate_on_screen(
        self, image_path: str, timeout: Optional[float] = None
    ) -> Optional[tuple[int, int]]:
        """
        Locate an image on screen

        Args:
            image_path: Path to image file
            timeout: Maximum time to search (uses default if None)

        Returns:
            Tuple of (x, y) coordinates if found, None otherwise
        """
        if not self.is_available():
            logger.warning(f"PyAutoGUI not available, would search for: {image_path}")
            return None

        search_timeout = timeout or self.search_timeout
        attempts = 0
        max_attempts = int(search_timeout * 4)  # Check every 0.25 seconds

        while attempts < max_attempts:
            try:
                location = self._pyautogui.locateCenterOnScreen(image_path)
                if location:
                    self._pyautogui.moveTo(location)
                    logger.info(f"Image {image_path} found at position: {location}")
                    return location
            except Exception as e:
                logger.debug(f"Error locating image: {e}")

            time.sleep(0.25)
            attempts += 1

        logger.warning(f"Image {image_path} not found after {search_timeout}s")
        return None

    def is_available(self) -> bool:
        """
        Check if automation services are available

        Returns:
            True if automation services are available
        """
        return self._pyautogui_available
