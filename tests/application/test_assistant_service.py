# -*- coding: utf-8 -*-
"""Tests for Application layer - Assistant Service"""

from unittest.mock import Mock

import pytest

from app.application.ports import ActionProvider, VoiceProvider, WebProvider
from app.application.services import AssistantService
from app.domain.services import CommandInterpreter, IntentProcessor


class TestAssistantService:
    """Test cases for AssistantService with mocked ports"""

    @pytest.fixture
    def mock_ports(self):
        """Create mocked ports"""
        voice = Mock(spec=VoiceProvider)
        action = Mock(spec=ActionProvider)
        web = Mock(spec=WebProvider)
        return voice, action, web

    @pytest.fixture
    def service(self, mock_ports):
        """Create AssistantService with mocked dependencies"""
        voice, action, web = mock_ports

        interpreter = CommandInterpreter(wake_word="test")
        processor = IntentProcessor()

        return AssistantService(
            voice_provider=voice,
            action_provider=action,
            web_provider=web,
            command_interpreter=interpreter,
            intent_processor=processor,
            wake_word="test",
        )

    def test_service_initialization(self, service):
        """Test that service initializes correctly"""
        assert service is not None
        assert service.wake_word == "test"
        assert service.is_running is False

    def test_process_type_command(self, service, mock_ports):
        """Test processing a type command"""
        _, action, _ = mock_ports

        response = service.process_command("escreva hello world")

        assert response.success is True
        action.type_text.assert_called_once_with("hello world")

    def test_process_press_key_command(self, service, mock_ports):
        """Test processing a press key command"""
        _, action, _ = mock_ports

        response = service.process_command("aperte enter")

        assert response.success is True
        action.press_key.assert_called_once_with("enter")

    def test_process_open_browser_command(self, service, mock_ports):
        """Test processing open browser command"""
        _, action, _ = mock_ports

        response = service.process_command("internet")

        assert response.success is True
        action.hotkey.assert_called_once_with("ctrl", "shift", "c")

    def test_process_open_url_command(self, service, mock_ports):
        """Test processing open URL command"""
        _, _, web = mock_ports

        response = service.process_command("site google.com")

        assert response.success is True
        web.open_url.assert_called_once_with("https://google.com")

    def test_process_search_command(self, service, mock_ports):
        """Test processing search on page command"""
        _, _, web = mock_ports

        response = service.process_command("clicar em botão")

        assert response.success is True
        web.search_on_page.assert_called_once_with("botão")

    def test_process_unknown_command(self, service):
        """Test processing unknown command returns error"""
        response = service.process_command("comando inexistente")

        assert response.success is False
        assert response.error == "UNKNOWN_COMMAND"

    def test_process_command_with_validation_error(self, service):
        """Test that commands requiring parameters are validated"""
        # Unknown command should fail
        response = service.process_command("comando inexistente xyz")

        assert response.success is False
        assert response.error == "UNKNOWN_COMMAND"

    def test_stop(self, service):
        """Test stop method"""
        service.is_running = True
        service.stop()

        assert service.is_running is False
