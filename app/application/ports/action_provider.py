# -*- coding: utf-8 -*-
"""Action Provider Port - Interface for system automation"""

from abc import ABC, abstractmethod
from typing import Optional


class ActionProvider(ABC):
    """
    Port (interface) for system automation actions.
    Adapters must implement this interface.
    """

    @abstractmethod
    def type_text(self, text: str) -> None:
        """
        Type text using keyboard

        Args:
            text: Text to type
        """
        pass

    @abstractmethod
    def press_key(self, key: str) -> None:
        """
        Press a keyboard key

        Args:
            key: Key name to press
        """
        pass

    @abstractmethod
    def press_keys(self, keys: list[str]) -> None:
        """
        Press multiple keys sequentially

        Args:
            keys: List of key names to press
        """
        pass

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """
        Press a hotkey combination

        Args:
            keys: Keys to press together
        """
        pass

    @abstractmethod
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        """
        Click at specific coordinates

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button ('left', 'right', 'middle')
            clicks: Number of clicks
        """
        pass

    @abstractmethod
    def locate_on_screen(
        self, image_path: str, timeout: Optional[float] = None
    ) -> Optional[tuple[int, int]]:
        """
        Locate an image on screen

        Args:
            image_path: Path to image file
            timeout: Maximum time to search

        Returns:
            Tuple of (x, y) coordinates if found, None otherwise
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if automation services are available

        Returns:
            True if automation services are available
        """
        pass
