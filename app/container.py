# -*- coding: utf-8 -*-
"""
Dependency Injection Container for Jarvis Assistant.
Provides factory functions for creating configured service containers.
"""

import os
import sys
from typing import Optional

from app.core.config import settings


def _is_headless_environment() -> bool:
    """
    Detect whether the current runtime is a headless (non-interactive) environment.

    Returns True when running in:
    - pytest (test runner)
    - CI/CD pipelines (CI env var)
    - GitHub Actions (GITHUB_ACTIONS env var)
    - Cloud platforms: Render (RENDER), Heroku (DYNO), Railway (RAILWAY_ENVIRONMENT)

    Returns:
        True if the environment is headless/cloud, False otherwise.
    """
    # Running under pytest
    if "pytest" in sys.modules:
        return True
    # CI/CD environment
    if os.environ.get("CI"):
        return True
    # GitHub Actions
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    # Render cloud platform
    if os.environ.get("RENDER"):
        return True
    # Heroku (DYNO is always set on Heroku dynos)
    if os.environ.get("DYNO"):
        return True
    # Railway
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return True
    return False


class Container:
    """
    Dependency injection container for Jarvis services.
    Auto-enables LLM when a valid API key is available.
    """

    def __init__(
        self,
        wake_word: Optional[str] = None,
        language: Optional[str] = None,
        use_llm: bool = False,
        gemini_api_key: Optional[str] = None,
    ):
        self.wake_word = wake_word or settings.wake_word
        self.language = language or settings.language
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
        # Auto-enable LLM when an API key is available
        self.use_llm = use_llm or bool(self.gemini_api_key)

        self._assistant_service = None
        self._extension_manager = None
        self._voice_provider = None

    @property
    def voice_provider(self):
        if self._voice_provider is None:
            if _is_headless_environment():
                from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
                self._voice_provider = DummyVoiceProvider()
            else:
                try:
                    from app.adapters.edge.combined_voice_provider import CombinedVoiceProvider
                    self._voice_provider = CombinedVoiceProvider()
                except Exception:
                    from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
                    self._voice_provider = DummyVoiceProvider()
        return self._voice_provider

    @property
    def assistant_service(self):
        if self._assistant_service is None:
            from app.application.services import AssistantService
            self._assistant_service = AssistantService()
        return self._assistant_service

    @property
    def extension_manager(self):
        if self._extension_manager is None:
            from app.application.services import ExtensionManager
            self._extension_manager = ExtensionManager()
        return self._extension_manager


# Alias for backward compatibility
EdgeContainer = Container


def create_edge_container(
    wake_word: Optional[str] = None,
    language: Optional[str] = None,
    use_llm: bool = False,
) -> Container:
    """
    Create and configure a container for edge deployment.

    Args:
        wake_word: Wake word for voice activation.
        language: Language code (e.g. 'pt-BR').
        use_llm: Whether to enable LLM integration.
                 Will be auto-enabled when an API key is available.

    Returns:
        Configured Container instance.
    """
    return Container(
        wake_word=wake_word,
        language=language,
        use_llm=use_llm,
    )
