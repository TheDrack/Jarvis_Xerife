# -*- coding: utf-8 -*-
"""Voice Adapter - Speech recognition implementation using Google Speech API"""

import logging
from typing import Optional

from app.application.ports import VoiceProvider

logger = logging.getLogger(__name__)


class VoiceAdapter(VoiceProvider):
    """
    Edge adapter for voice recognition using SpeechRecognition library.
    Depends on microphone hardware and Google Speech API.
    """

    def __init__(
        self,
        language: str = "pt-BR",
        ambient_noise_adjustment: bool = True,
    ):
        """
        Initialize voice adapter

        Args:
            language: Language code for recognition
            ambient_noise_adjustment: Whether to adjust for ambient noise
        """
        # Lazy import of speech_recognition to reduce startup memory usage
        try:
            import speech_recognition as sr
            self._sr = sr
            self._speech_recognition_available = True
            self.recognizer = sr.Recognizer()
        except ImportError:
            logger.warning("speech_recognition module not available")
            self._sr = None
            self._speech_recognition_available = False
            self.recognizer = None

        self.language = language
        self.ambient_noise_adjustment = ambient_noise_adjustment

    def speak(self, text: str) -> None:
        """
        This adapter only handles recognition, not synthesis.
        Use TTSAdapter for text-to-speech.

        Args:
            text: Text to be spoken (ignored)
        """
        logger.debug("VoiceAdapter.speak called but not implemented (use TTSAdapter)")

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Listen for voice input and convert to text

        Args:
            timeout: Maximum time to wait for speech (seconds)

        Returns:
            Recognized text or None if recognition failed
        """
        if not self.is_available():
            logger.error("Voice recognition not available")
            return None

        try:
            with self._sr.Microphone() as source:
                if self.ambient_noise_adjustment:
                    self.recognizer.adjust_for_ambient_noise(source)

                audio = self.recognizer.listen(source, timeout=timeout)

                # Try to recognize with show_all first to check if anything was detected
                result = self.recognizer.recognize_google(
                    audio, language=self.language, show_all=True
                )

                if result:
                    # Get the best match
                    command = self.recognizer.recognize_google(audio, language=self.language)
                    return command.lower()
                return None

        except self._sr.WaitTimeoutError:
            return None
        except self._sr.UnknownValueError:
            return None
        except self._sr.RequestError as e:
            logger.error(f"Could not request results from Google Speech Recognition: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in voice recognition: {e}")
            return None

    def is_available(self) -> bool:
        """
        Check if voice services are available

        Returns:
            True if voice services are available
        """
        return self._speech_recognition_available and self.recognizer is not None
