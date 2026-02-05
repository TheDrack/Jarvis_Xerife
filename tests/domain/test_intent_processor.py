# -*- coding: utf-8 -*-
"""Tests for Domain layer - Intent Processor"""

import pytest

from app.domain.models import CommandType, Intent
from app.domain.services import IntentProcessor


class TestIntentProcessor:
    """Test cases for IntentProcessor - pure business logic"""

    @pytest.fixture
    def processor(self):
        """Create an IntentProcessor instance"""
        return IntentProcessor()

    def test_create_command(self, processor):
        """Test command creation from intent"""
        intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
            raw_input="escreva hello",
        )

        command = processor.create_command(intent)

        assert command.intent == intent
        assert command.timestamp is not None
        assert isinstance(command.context, dict)

    def test_create_command_with_context(self, processor):
        """Test command creation with custom context"""
        intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
        )
        context = {"user_id": "123", "session": "abc"}

        command = processor.create_command(intent, context)

        assert command.context == context

    def test_validate_unknown_command(self, processor):
        """Test validation fails for unknown commands"""
        intent = Intent(
            command_type=CommandType.UNKNOWN,
            parameters={},
        )

        response = processor.validate_intent(intent)

        assert response.success is False
        assert response.error == "UNKNOWN_COMMAND"

    def test_validate_type_text_without_text(self, processor):
        """Test validation fails when text parameter is missing"""
        intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={},
        )

        response = processor.validate_intent(intent)

        assert response.success is False
        assert response.error == "MISSING_PARAMETER"

    def test_validate_type_text_with_text(self, processor):
        """Test validation succeeds when text parameter is present"""
        intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
        )

        response = processor.validate_intent(intent)

        assert response.success is True

    def test_validate_press_key_without_key(self, processor):
        """Test validation fails when key parameter is missing"""
        intent = Intent(
            command_type=CommandType.PRESS_KEY,
            parameters={},
        )

        response = processor.validate_intent(intent)

        assert response.success is False
        assert response.error == "MISSING_PARAMETER"

    def test_validate_open_url_without_url(self, processor):
        """Test validation fails when URL parameter is missing"""
        intent = Intent(
            command_type=CommandType.OPEN_URL,
            parameters={},
        )

        response = processor.validate_intent(intent)

        assert response.success is False

    def test_validate_open_browser(self, processor):
        """Test validation succeeds for open browser (no params needed)"""
        intent = Intent(
            command_type=CommandType.OPEN_BROWSER,
            parameters={},
        )

        response = processor.validate_intent(intent)

        assert response.success is True

    def test_should_provide_feedback(self, processor):
        """Test feedback determination for different command types"""
        # Commands that should NOT provide feedback
        assert processor.should_provide_feedback(CommandType.TYPE_TEXT) is False
        assert processor.should_provide_feedback(CommandType.PRESS_KEY) is False

        # Commands that SHOULD provide feedback
        assert processor.should_provide_feedback(CommandType.OPEN_BROWSER) is True
        assert processor.should_provide_feedback(CommandType.OPEN_URL) is True
        assert processor.should_provide_feedback(CommandType.SEARCH_ON_PAGE) is True
