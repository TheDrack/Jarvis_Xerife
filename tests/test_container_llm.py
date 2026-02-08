# -*- coding: utf-8 -*-
"""Tests for Container LLM adapter initialization"""

import os
from unittest.mock import patch

import pytest

from app.container import Container, create_edge_container


class TestContainerLLMInitialization:
    """Test cases for LLM adapter initialization based on API key availability"""

    def test_container_enables_llm_when_api_key_provided(self):
        """Test that Container enables LLM when API key is provided"""
        container = Container(
            gemini_api_key="test-api-key-123",
            use_llm=False,  # Explicitly disabled
        )
        # Should be enabled because API key is present
        assert container.use_llm is True
        assert container.gemini_api_key == "test-api-key-123"

    def test_container_respects_use_llm_true(self):
        """Test that Container respects explicit use_llm=True"""
        container = Container(
            use_llm=True,
            gemini_api_key="test-api-key-123",
        )
        assert container.use_llm is True

    def test_container_disables_llm_when_no_api_key(self):
        """Test that Container disables LLM when no API key is provided"""
        with patch.dict(os.environ, {}, clear=False):
            # Clear GEMINI_API_KEY if it exists
            os.environ.pop("GEMINI_API_KEY", None)
            container = Container(
                use_llm=False,
                gemini_api_key=None,
            )
            assert container.use_llm is False
            assert container.gemini_api_key is None

    def test_container_reads_api_key_from_env(self):
        """Test that Container reads API key from environment"""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-api-key"}):
            container = Container(use_llm=False)
            # Should enable LLM because env var has API key
            assert container.use_llm is True
            assert container.gemini_api_key == "env-api-key"

    def test_create_edge_container_auto_enables_llm_with_api_key(self):
        """Test that create_edge_container auto-enables LLM when API key in settings"""
        # Mock settings to have an API key
        with patch("app.container.settings") as mock_settings:
            mock_settings.gemini_api_key = "settings-api-key"
            mock_settings.gemini_model = "gemini-1.5-flash"
            
            container = create_edge_container(use_llm=False)
            
            # Should be enabled because settings has API key
            assert container.use_llm is True
            assert container.gemini_api_key == "settings-api-key"

    def test_create_edge_container_without_api_key(self):
        """Test that create_edge_container doesn't enable LLM without API key"""
        with patch("app.container.settings") as mock_settings:
            mock_settings.gemini_api_key = None
            mock_settings.gemini_model = "gemini-1.5-flash"
            
            container = create_edge_container(use_llm=False)
            
            # Should remain disabled
            assert container.use_llm is False
            assert container.gemini_api_key is None
