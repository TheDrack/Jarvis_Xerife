# -*- coding: utf-8 -*-
"""Tests for main.py cloud mode initialization"""

import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock hardware-dependent modules before importing main
sys.modules['pyautogui'] = MagicMock()
sys.modules['pyttsx3'] = MagicMock()
sys.modules['speech_recognition'] = MagicMock()
sys.modules['uvicorn'] = MagicMock()


class TestMainCloudMode:
    """Test cases for main.py cloud mode"""

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('app.container.create_edge_container')
    @patch.dict('os.environ', {'PORT': '8000'})
    def test_start_cloud_creates_container(
        self, mock_create_container, mock_create_api, mock_uvicorn
    ):
        """Test that start_cloud_service creates a container"""
        mock_container = Mock()
        mock_assistant = Mock()
        mock_container.assistant_service = mock_assistant
        mock_create_container.return_value = mock_container
        mock_create_api.return_value = Mock()

        import main

        main.start_cloud_service()

        mock_create_container.assert_called_once()
        mock_create_api.assert_called_once_with(mock_assistant)
        mock_uvicorn.assert_called_once()

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('app.container.create_edge_container')
    @patch.dict('os.environ', {'PORT': '9000'})
    def test_start_cloud_uses_custom_port(
        self, mock_create_container, mock_create_api, mock_uvicorn
    ):
        """Test that start_cloud_service uses PORT environment variable"""
        mock_container = Mock()
        mock_container.assistant_service = Mock()
        mock_create_container.return_value = mock_container
        mock_create_api.return_value = Mock()

        import main

        main.start_cloud_service()

        call_args = mock_uvicorn.call_args
        assert call_args[1]['port'] == 9000

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('app.container.create_edge_container')
    @patch.dict('os.environ', {}, clear=True)
    def test_start_cloud_default_port(
        self, mock_create_container, mock_create_api, mock_uvicorn
    ):
        """Test that start_cloud_service uses default port when PORT not set"""
        mock_container = Mock()
        mock_container.assistant_service = Mock()
        mock_create_container.return_value = mock_container
        mock_create_api.return_value = Mock()

        import main

        main.start_cloud_service()

        call_args = mock_uvicorn.call_args
        assert call_args[1]['port'] == 10000

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('app.container.create_edge_container')
    def test_start_cloud_passes_wake_word_and_language_to_container(
        self, mock_create_container, mock_create_api, mock_uvicorn
    ):
        """Test that start_cloud_service passes wake_word and language settings to container"""
        mock_container = Mock()
        mock_container.assistant_service = Mock()
        mock_create_container.return_value = mock_container
        mock_create_api.return_value = Mock()

        import main
        from app.core.config import settings

        main.start_cloud_service()

        mock_create_container.assert_called_once_with(
            wake_word=settings.wake_word,
            language=settings.language,
        )


class TestBootstrapServicesOrder:
    """Tests that bootstrap_background_services starts OverwatchDaemon before polling."""

    def test_overwatch_daemon_starts_before_polling(self):
        """OverwatchDaemon must be started before telegram.start_polling is called."""
        call_order = []

        mock_daemon = MagicMock()
        mock_daemon.start.side_effect = lambda: call_order.append("daemon_start")

        mock_telegram = MagicMock()
        mock_telegram.start_polling.side_effect = lambda **kwargs: call_order.append("polling_start")

        mock_assistant = MagicMock()
        mock_nexus = MagicMock()
        mock_nexus.resolve.side_effect = lambda name: (
            mock_assistant if name == "assistant_service" else mock_telegram
        )

        import main

        with (
            patch.object(main, "_OVERWATCH_AVAILABLE", True),
            patch("main.OverwatchDaemon", return_value=mock_daemon),
            patch("main.nexus", mock_nexus),
            patch("main.send_dynamic_startup_notification"),
            patch.dict("os.environ", {}, clear=True),
        ):
            main.bootstrap_background_services()

        assert "daemon_start" in call_order, "OverwatchDaemon.start() was never called"
        assert "polling_start" in call_order, "start_polling was never called"
        assert call_order.index("daemon_start") < call_order.index("polling_start"), (
            f"Expected daemon_start before polling_start, got: {call_order}"
        )

    def test_overwatch_daemon_notify_activity_called_on_message(self):
        """telegram_callback should call notify_activity on the daemon instance."""
        mock_daemon = MagicMock()
        mock_assistant = MagicMock()
        mock_assistant.process_command.return_value = "ok"

        captured_callback = {}

        def fake_start_polling(callback):
            captured_callback["cb"] = callback

        mock_telegram = MagicMock()
        mock_telegram.start_polling.side_effect = fake_start_polling

        mock_nexus = MagicMock()
        mock_nexus.resolve.side_effect = lambda name: (
            mock_assistant if name == "assistant_service" else mock_telegram
        )

        import main

        with (
            patch.object(main, "_OVERWATCH_AVAILABLE", True),
            patch("main.OverwatchDaemon", return_value=mock_daemon),
            patch("main.nexus", mock_nexus),
            patch("main.send_dynamic_startup_notification"),
            patch.dict("os.environ", {}, clear=True),
        ):
            main.bootstrap_background_services()

        assert "cb" in captured_callback, "telegram_callback was not registered"
        captured_callback["cb"]("hello", "chat123")
        mock_daemon.notify_activity.assert_called_once()
