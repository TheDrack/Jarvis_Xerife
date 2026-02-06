# -*- coding: utf-8 -*-
"""Tests for Application layer - Assistant Service"""

from unittest.mock import Mock

import pytest

from app.application.ports import ActionProvider, VoiceProvider, WebProvider
from app.application.services import AssistantService, DependencyManager
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

    def test_command_history_empty(self, service):
        """Test get_command_history returns empty list initially"""
        history = service.get_command_history()

        assert history == []

    def test_command_history_tracking(self, service, mock_ports):
        """Test that commands are added to history"""
        _, action, _ = mock_ports

        # Execute a command
        service.process_command("escreva hello")

        # Check history
        history = service.get_command_history(limit=5)

        assert len(history) == 1
        assert history[0]["command"] == "escreva hello"
        assert history[0]["success"] is True
        assert "timestamp" in history[0]
        assert "message" in history[0]

    def test_command_history_limit(self, service, mock_ports):
        """Test that history respects limit parameter"""
        _, action, _ = mock_ports

        # Execute multiple commands
        for i in range(10):
            service.process_command(f"escreva test{i}")

        # Get limited history
        history = service.get_command_history(limit=3)

        assert len(history) == 3
        # Most recent should be first
        assert history[0]["command"] == "escreva test9"
        assert history[1]["command"] == "escreva test8"
        assert history[2]["command"] == "escreva test7"

    def test_command_history_failed_commands(self, service):
        """Test that failed commands are also tracked in history"""
        # Execute invalid command
        service.process_command("invalid command")

        # Check history
        history = service.get_command_history(limit=5)

        assert len(history) == 1
        assert history[0]["command"] == "invalid command"
        assert history[0]["success"] is False

    def test_dependency_manager_auto_created(self, service):
        """Test that dependency manager is auto-created if not provided"""
        assert service.dependency_manager is not None
        assert isinstance(service.dependency_manager, DependencyManager)

    def test_dependency_manager_injection(self, mock_ports):
        """Test that dependency manager can be injected"""
        voice, action, web = mock_ports
        mock_dep_manager = Mock(spec=DependencyManager)

        interpreter = CommandInterpreter(wake_word="test")
        processor = IntentProcessor()

        service = AssistantService(
            voice_provider=voice,
            action_provider=action,
            web_provider=web,
            command_interpreter=interpreter,
            intent_processor=processor,
            dependency_manager=mock_dep_manager,
            wake_word="test",
        )

        assert service.dependency_manager is mock_dep_manager
