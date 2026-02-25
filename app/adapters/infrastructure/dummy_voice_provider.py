from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Dummy Voice Provider - Headless voice provider for testing and cloud environments"""

import logging
from typing import Optional

from app.application.ports import VoiceProvider

logger = logging.getLogger(__name__)


class DummyVoiceProvider(NexusComponent, VoiceProvider):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Dummy voice provider for environments without audio hardware.
    Used in tests, CI/CD, and cloud deployments (like Render).
    Logs voice operations instead of performing them.
    """

    def __init__(self):
        """Initialize dummy voice provider"""
        logger.info("DummyVoiceProvider initialized (headless mode)")

    def speak(self, text: str) -> None:
        """
        Log text that would be spoken

        Args:
            text: Text to be spoken
        """
        logger.info(f"[DummyVoiceProvider.speak]: {text}")
        print(f"[VOICE]: {text}")

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Return None as there's no audio input in headless mode

        Args:
            timeout: Maximum time to wait for speech (seconds)

        Returns:
            None (no audio input available)
        """
        logger.debug("DummyVoiceProvider.listen called (headless mode, returning None)")
        return None

    def is_available(self) -> bool:
        """
        Check if voice services are available

        Returns:
            True (always available as a dummy provider)
        """
        return True
