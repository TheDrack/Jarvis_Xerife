# -*- coding: utf-8 -*-
"""Combined Voice Provider - Combines TTS and Voice recognition"""

import logging
from typing import Optional

from app.adapters.edge.tts_adapter import TTSAdapter
from app.adapters.edge.voice_adapter import VoiceAdapter
from app.application.ports import VoiceProvider

logger = logging.getLogger(__name__)


class CombinedVoiceProvider(VoiceProvider):
    """
    Combines TTS and Voice recognition adapters into a single provider.
    This is a convenience adapter for edge deployments.
    """

    def __init__(
        self,
        language: str = "pt-BR",
        ambient_noise_adjustment: bool = True,
    ):
        """
        Initialize combined voice provider

        Args:
            language: Language code for recognition
            ambient_noise_adjustment: Whether to adjust for ambient noise
        """
        self.tts = TTSAdapter()
        self.voice = VoiceAdapter(language, ambient_noise_adjustment)

    def speak(self, text: str) -> None:
        """
        Convert text to speech

        Args:
            text: Text to be spoken
        """
        self.tts.speak(text)

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Listen for voice input and convert to text

        Args:
            timeout: Maximum time to wait for speech (seconds)

        Returns:
            Recognized text or None if recognition failed
        """
        return self.voice.listen(timeout)

    def is_available(self) -> bool:
        """
        Check if voice services are available

        Returns:
            True if both TTS and voice recognition are available
        """
        return self.tts.is_available() or self.voice.is_available()
