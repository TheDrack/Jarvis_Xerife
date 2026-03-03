# -*- coding: utf-8 -*-
"""Tests for VisionAdapter - Happy Path validation"""

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.infrastructure.vision_adapter import VisionAdapter


class TestVisionAdapter:
    """Tests for VisionAdapter with mocked external dependencies."""

    @pytest.fixture
    def adapter(self):
        return VisionAdapter(api_key="test-api-key", use_webcam=False)

    def test_initialization_defaults(self):
        adapter = VisionAdapter(api_key="key123")
        assert adapter._api_key == "key123"
        assert adapter._use_webcam is False
        assert "flash" in adapter._vision_model

    def test_execute_returns_dict(self, adapter):
        with patch.object(adapter, "capture_and_analyze", return_value="Usuário está codando."):
            result = adapter.execute()
        assert result["success"] is True
        assert result["description"] == "Usuário está codando."

    def test_execute_returns_failure_on_none(self, adapter):
        with patch.object(adapter, "capture_and_analyze", return_value=None):
            result = adapter.execute()
        assert result["success"] is False
        assert result["description"] is None

    def test_capture_and_analyze_returns_description(self, adapter):
        fake_image = b"\x89PNG..."
        with patch.object(adapter, "_capture_image", return_value=fake_image):
            with patch.object(adapter, "_analyze_with_gemini", return_value="Tela de editor de código."):
                desc = adapter.capture_and_analyze()
        assert desc == "Tela de editor de código."

    def test_capture_and_analyze_returns_none_when_no_image(self, adapter):
        with patch.object(adapter, "_capture_image", return_value=None):
            desc = adapter.capture_and_analyze()
        assert desc is None

    def test_analyze_with_gemini_no_api_key(self):
        adapter = VisionAdapter(api_key=None)
        # Ensure env var is not set
        import os
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        result = adapter._analyze_with_gemini(b"fake", "descricao")
        assert result is None

    def test_capture_screenshot_fallback_on_no_mss(self, adapter):
        """If mss and PIL are unavailable, _capture_screenshot returns None gracefully."""
        with patch.dict("sys.modules", {"mss": None, "PIL": None, "PIL.ImageGrab": None}):
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                result = adapter._capture_screenshot()
        assert result is None
