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
    """Detect whether the current runtime is a headless (non-interactive) environment."""
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
    """Thin compatibility wrapper around JarvisNexus."""

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
        self.use_llm = use_llm or bool(self.gemini_api_key)

    @property
    def voice_provider(self):
        if _is_headless_environment():
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
            return DummyVoiceProvider()

        resolved = nexus.resolve("voice_adapter")
        if resolved is None or getattr(resolved, "__is_cloud_mock__", False):
            from app.adapters.infrastructure.dummy_voice_provider import DummyVoiceProvider
            return DummyVoiceProvider()
        return resolved

    @property
    def assistant_service(self):
        """Resolve via JarvisNexus and discard CloudMock instances."""
        resolved = nexus.resolve("assistant_service")
        if resolved is not None and getattr(resolved, "__is_cloud_mock__", False):
            return None
        return resolved

    @property
    def extension_manager(self):
        """Resolve via JarvisNexus and discard CloudMock instances."""
        resolved = nexus.resolve("extension_manager")
        if resolved is not None and getattr(resolved, "__is_cloud_mock__", False):
            return None
        return resolved


EdgeContainer = Container


def create_edge_container(
    wake_word: Optional[str] = None,
    language: Optional[str] = None,
    use_llm: bool = False,
) -> Container:
    return Container(
        wake_word=wake_word,
        language=language,
        use_llm=use_llm,
    )
