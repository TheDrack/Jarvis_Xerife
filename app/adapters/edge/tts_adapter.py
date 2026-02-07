# -*- coding: utf-8 -*-
"""TTS Adapter - Text-to-speech implementation using pyttsx3"""

import logging
from typing import Optional

from app.application.ports import VoiceProvider

logger = logging.getLogger(__name__)


class TTSAdapter(VoiceProvider):
    """
    Edge adapter for text-to-speech using pyttsx3 library.
    Depends on system audio drivers.
    """

    def __init__(self):
        """Initialize TTS adapter"""
        # Lazy import of pyttsx3 to reduce startup memory usage
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3
            self._pyttsx3_available = True
            try:
                self.engine = pyttsx3.init()
            except Exception as e:
                logger.error(f"Failed to initialize pyttsx3: {e}")
                self.engine = None
        except ImportError:
            logger.warning("pyttsx3 module not available")
            self._pyttsx3 = None
            self._pyttsx3_available = False
            self.engine = None

    def speak(self, text: str) -> None:
        """
        Convert text to speech

        Args:
            text: Text to be spoken
        """
        if not self.is_available():
            logger.warning(f"TTS not available, would speak: {text}")
            print(f"[TTS]: {text}")
            return

        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}")

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        This adapter only handles synthesis, not recognition.
        Use VoiceAdapter for speech recognition.

        Args:
            timeout: Not used

        Returns:
            None
        """
        logger.debug("TTSAdapter.listen called but not implemented (use VoiceAdapter)")
        return None

    def is_available(self) -> bool:
        """
        Check if TTS services are available

        Returns:
            True if TTS services are available
        """
        return self._pyttsx3_available and self.engine is not None
