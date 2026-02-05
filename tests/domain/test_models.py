# -*- coding: utf-8 -*-
"""Tests for Domain models"""

import pytest

from app.domain.models import Command, CommandType, Intent, Response


class TestIntent:
    """Test cases for Intent model"""

    def test_create_intent(self):
        """Test intent creation"""
        intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
            raw_input="escreva hello",
            confidence=0.9,
        )

        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "hello"
        assert intent.raw_input == "escreva hello"
        assert intent.confidence == 0.9

    def test_intent_default_values(self):
        """Test intent default values"""
        intent = Intent(command_type=CommandType.UNKNOWN)

        assert intent.parameters == {}
        assert intent.raw_input == ""
        assert intent.confidence == 1.0

    def test_intent_confidence_validation(self):
        """Test that confidence must be between 0 and 1"""
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            Intent(command_type=CommandType.TYPE_TEXT, confidence=1.5)

        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            Intent(command_type=CommandType.TYPE_TEXT, confidence=-0.1)


class TestCommand:
    """Test cases for Command model"""

    def test_create_command(self):
        """Test command creation"""
        intent = Intent(command_type=CommandType.TYPE_TEXT)
        command = Command(
            intent=intent,
            timestamp="2024-01-01T00:00:00",
            context={"user": "test"},
        )

        assert command.intent == intent
        assert command.timestamp == "2024-01-01T00:00:00"
        assert command.context["user"] == "test"

    def test_command_default_values(self):
        """Test command default values"""
        intent = Intent(command_type=CommandType.TYPE_TEXT)
        command = Command(intent=intent)

        assert command.timestamp is None
        assert command.context == {}


class TestResponse:
    """Test cases for Response model"""

    def test_create_success_response(self):
        """Test success response creation"""
        response = Response(success=True, message="Done")

        assert response.success is True
        assert response.message == "Done"
        assert response.data is None
        assert response.error is None

    def test_create_error_response(self):
        """Test error response creation"""
        response = Response(
            success=False,
            message="Failed",
            error="ERROR_CODE",
        )

        assert response.success is False
        assert response.message == "Failed"
        assert response.error == "ERROR_CODE"

    def test_response_default_message(self):
        """Test that default messages are set based on success"""
        success_response = Response(success=True)
        error_response = Response(success=False)

        assert success_response.message == "Command executed successfully"
        assert error_response.message == "Command failed"

    def test_response_with_data(self):
        """Test response with data payload"""
        response = Response(
            success=True,
            data={"result": "value", "count": 5},
        )

        assert response.data["result"] == "value"
        assert response.data["count"] == 5


class TestCommandType:
    """Test cases for CommandType enum"""

    def test_command_types(self):
        """Test that all command types exist"""
        assert CommandType.TYPE_TEXT.value == "type_text"
        assert CommandType.PRESS_KEY.value == "press_key"
        assert CommandType.OPEN_BROWSER.value == "open_browser"
        assert CommandType.OPEN_URL.value == "open_url"
        assert CommandType.SEARCH_ON_PAGE.value == "search_on_page"
        assert CommandType.UNKNOWN.value == "unknown"
