# -*- coding: utf-8 -*-
"""Voice Provider Port - Interface for voice input/output"""

from abc import ABC, abstractmethod
from typing import Optional


class VoiceProvider(ABC):
    """
    Port (interface) for voice recognition and synthesis.
    Adapters must implement this interface.
    """

    @abstractmethod
    def speak(self, text: str) -> None:
        """
        Convert text to speech

        Args:
            text: Text to be spoken
        """
        pass

    @abstractmethod
    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Listen for voice input and convert to text

        Args:
            timeout: Maximum time to wait for speech (seconds)

        Returns:
            Recognized text or None if recognition failed
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if voice services are available

        Returns:
            True if voice services are available
        """
        pass
