# -*- coding: utf-8 -*-
"""Tests for main.py cloud mode initialization"""

import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock hardware-dependent modules before importing main
sys.modules['pyautogui'] = MagicMock()
sys.modules['pyttsx3'] = MagicMock()
sys.modules['speech_recognition'] = MagicMock()


class TestMainCloudMode:
    """Test cases for main.py cloud mode"""

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('main.create_edge_container')
    @patch.dict('os.environ', {'PORT': '8000'})
    def test_start_cloud_creates_container(self, mock_create_container, mock_create_api, mock_uvicorn):
        """Test that start_cloud creates a container"""
        # Setup mocks
        mock_container = Mock()
        mock_assistant = Mock()
        mock_container.assistant_service = mock_assistant
        mock_create_container.return_value = mock_container
        mock_app = Mock()
        mock_create_api.return_value = mock_app
        
        # Import after mocking
        import main
        
        # Call start_cloud
        main.start_cloud()
        
        # Verify container was created
        mock_create_container.assert_called_once()
        # Verify assistant service was retrieved
        assert mock_container.assistant_service
        # Verify API server was created with assistant service
        mock_create_api.assert_called_once_with(mock_assistant)
        # Verify uvicorn was started
        mock_uvicorn.assert_called_once()

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('main.create_edge_container')
    @patch.dict('os.environ', {'PORT': '9000'})
    def test_start_cloud_uses_custom_port(self, mock_create_container, mock_create_api, mock_uvicorn):
        """Test that start_cloud uses PORT environment variable"""
        # Setup mocks
        mock_container = Mock()
        mock_assistant = Mock()
        mock_container.assistant_service = mock_assistant
        mock_create_container.return_value = mock_container
        mock_app = Mock()
        mock_create_api.return_value = mock_app
        
        # Import after mocking
        import main
        
        # Call start_cloud
        main.start_cloud()
        
        # Verify uvicorn was started with correct port
        call_args = mock_uvicorn.call_args
        assert call_args[1]['port'] == 9000

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('main.create_edge_container')
    @patch.dict('os.environ', {}, clear=True)
    def test_start_cloud_default_port(self, mock_create_container, mock_create_api, mock_uvicorn):
        """Test that start_cloud uses default port when PORT not set"""
        # Setup mocks
        mock_container = Mock()
        mock_assistant = Mock()
        mock_container.assistant_service = mock_assistant
        mock_create_container.return_value = mock_container
        mock_app = Mock()
        mock_create_api.return_value = mock_app
        
        # Import after mocking
        import main
        
        # Call start_cloud
        main.start_cloud()
        
        # Verify uvicorn was started with default port
        call_args = mock_uvicorn.call_args
        assert call_args[1]['port'] == 8000

    @patch('main.uvicorn.run')
    @patch('main.create_api_server')
    @patch('main.create_edge_container')
    def test_start_cloud_passes_wake_word_and_language_to_container(self, mock_create_container, mock_create_api, mock_uvicorn):
        """Test that start_cloud passes wake_word and language settings to container"""
        # Setup mocks
        mock_container = Mock()
        mock_assistant = Mock()
        mock_container.assistant_service = mock_assistant
        mock_create_container.return_value = mock_container
        mock_app = Mock()
        mock_create_api.return_value = mock_app
        
        # Import after mocking
        import main
        from app.core.config import settings
        
        # Call start_cloud
        main.start_cloud()
        
        # Verify container was created with settings
        mock_create_container.assert_called_once_with(
            wake_word=settings.wake_word,
            language=settings.language,
        )
