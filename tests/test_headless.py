# -*- coding: utf-8 -*-
"""Tests for Container and headless mode detection"""

import os
import sys
from unittest.mock import patch

import pytest

from app.adapters.infrastructure import DummyVoiceProvider
from app.container import _is_headless_environment, create_edge_container


class TestHeadlessEnvironment:
    """Test cases for headless environment detection and DummyVoiceProvider"""

    def test_headless_detection_with_pytest(self):
        """Test that pytest environment is detected as headless"""
        # pytest is already in sys.modules when running tests
        assert _is_headless_environment() is True

    def test_headless_detection_with_ci(self):
        """Test that CI environment is detected as headless"""
        with patch.dict(os.environ, {"CI": "true"}):
            assert _is_headless_environment() is True

    def test_headless_detection_with_github_actions(self):
        """Test that GitHub Actions environment is detected as headless"""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert _is_headless_environment() is True

    def test_headless_detection_with_render(self):
        """Test that Render cloud environment is detected as headless"""
        with patch.dict(os.environ, {"PORT": "8000", "RENDER": "true"}):
            assert _is_headless_environment() is True

    def test_headless_detection_with_heroku(self):
        """Test that Heroku cloud environment is detected as headless"""
        with patch.dict(os.environ, {"PORT": "8000", "DYNO": "web.1"}):
            assert _is_headless_environment() is True

    def test_headless_detection_port_only_not_headless(self):
        """Test that PORT alone (without cloud indicators) is not considered headless"""
        # Clear all other environment variables that might trigger headless
        with patch.dict(os.environ, {"PORT": "8000"}, clear=True):
            # Remove pytest from modules temporarily
            pytest_module = sys.modules.pop("pytest", None)
            try:
                # Should return False because PORT alone is not enough
                assert _is_headless_environment() is False
            finally:
                # Restore pytest module
                if pytest_module is not None:
                    sys.modules["pytest"] = pytest_module

    def test_container_uses_dummy_provider_in_headless(self):
        """Test that container uses DummyVoiceProvider in headless environment"""
        # We're already in a headless environment (pytest)
        container = create_edge_container()
        assert isinstance(container.voice_provider, DummyVoiceProvider)

    def test_dummy_voice_provider_speak(self):
        """Test DummyVoiceProvider speak method"""
        provider = DummyVoiceProvider()
        # Should not raise any exception
        provider.speak("Test message")

    def test_dummy_voice_provider_listen(self):
        """Test DummyVoiceProvider listen method"""
        provider = DummyVoiceProvider()
        # Should return None (no audio input in headless mode)
        result = provider.listen()
        assert result is None

    def test_dummy_voice_provider_is_available(self):
        """Test DummyVoiceProvider is_available method"""
        provider = DummyVoiceProvider()
        # Should always return True as it's a dummy provider
        assert provider.is_available() is True
