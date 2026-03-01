# -*- coding: utf-8 -*-
"""
Nexus-backed compatibility shim for Jarvis service resolution.

Service instantiation is owned by JarvisNexus (app.core.nexus).
This module exposes _is_headless_environment(), Container, and
create_edge_container() for backward compatibility with existing tests
and scripts that import from app.container.
"""

import os
import sys
from typing import Optional

from app.core.config import settings
from app.core.nexus import nexus


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
    if "pytest" in sys.modules:
        return True
    if os.environ.get("CI"):
        return True
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    if os.environ.get("RENDER"):
        return True
    if os.environ.get("DYNO"):
        return True
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return True
    return False


class Container:
    """
    Thin compatibility wrapper around JarvisNexus.

    All service resolution is delegated to nexus.resolve().
    Kept for backward compatibility with tests and scripts that
    reference Container directly.
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

    @property
    def voice_provider(self):
        if _is_headless_environment():
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
            return DummyVoiceProvider()
        resolved = nexus.resolve("voice_adapter")
        if resolved is None:
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
            return DummyVoiceProvider()
        return resolved

    @property
    def assistant_service(self):
        """Resolve via JarvisNexus. Returns None if the service cannot be located."""
        return nexus.resolve("assistant_service")

    @property
    def extension_manager(self):
        """Resolve via JarvisNexus. Returns None if the service cannot be located."""
        return nexus.resolve("extension_manager")


# Alias for backward compatibility
EdgeContainer = Container


def create_edge_container(
    wake_word: Optional[str] = None,
    language: Optional[str] = None,
    use_llm: bool = False,
) -> Container:
    """
    Create a Nexus-backed Container.

    Args:
        wake_word: Wake word for voice activation.
        language: Language code (e.g. 'pt-BR').
        use_llm: Whether to enable LLM integration.
                 Will be auto-enabled when an API key is available.

    Returns:
        Container that delegates service resolution to JarvisNexus.
    """
    return Container(
        wake_word=wake_word,
        language=language,
        use_llm=use_llm,
    )

