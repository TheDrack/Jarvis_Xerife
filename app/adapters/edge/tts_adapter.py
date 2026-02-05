# -*- coding: utf-8 -*-
"""TTS Adapter - Text-to-speech implementation using pyttsx3"""

import logging
from typing import Optional

try:
    import pyttsx3

    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

from app.application.ports import VoiceProvider

logger = logging.getLogger(__name__)


class TTSAdapter(VoiceProvider):
    """
    Edge adapter for text-to-speech using pyttsx3 library.
    Depends on system audio drivers.
    """

    def __init__(self):
        """Initialize TTS adapter"""
        if not PYTTSX3_AVAILABLE:
            logger.warning("pyttsx3 module not available")
            self.engine = None
        else:
            try:
                self.engine = pyttsx3.init()
            except Exception as e:
                logger.error(f"Failed to initialize pyttsx3: {e}")
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
        return PYTTSX3_AVAILABLE and self.engine is not None
