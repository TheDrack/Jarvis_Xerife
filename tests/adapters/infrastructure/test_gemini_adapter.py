# -*- coding: utf-8 -*-
"""Tests for Infrastructure layer - LLM Command Adapter"""

import os
from unittest.mock import Mock, patch

import pytest

from app.domain.models import CommandType


class TestLLMCommandAdapter:
    """Test cases for LLMCommandAdapter - Gemini API integration"""

    @pytest.fixture
    def mock_genai(self):
        """Mock google.generativeai module"""
        with patch("app.adapters.infrastructure.gemini_adapter.genai") as mock:
            # Mock the configure method
            mock.configure = Mock()

            # Mock the GenerativeModel
            mock_model = Mock()
            mock.GenerativeModel = Mock(return_value=mock_model)

            # Mock the chat
            mock_chat = Mock()
            mock_model.start_chat = Mock(return_value=mock_chat)

            yield mock, mock_model, mock_chat

    @pytest.fixture
    def mock_voice_provider(self):
        """Mock VoiceProvider"""
        voice = Mock()
        voice.speak = Mock()
        return voice

    def test_initialization_with_api_key(self, mock_genai):
        """Test LLMCommandAdapter initialization with API key"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        adapter = LLMCommandAdapter(api_key="test_api_key", wake_word="xerife")

        assert adapter.api_key == "test_api_key"
        assert adapter.wake_word == "xerife"
        assert adapter.model_name == "gemini-1.5-flash"
        mock_genai_module.configure.assert_called_once_with(api_key="test_api_key")

    def test_initialization_from_env(self, mock_genai):
        """Test LLMCommandAdapter initialization from environment variable"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, _, _ = mock_genai

        with patch.dict(os.environ, {"GEMINI_API_KEY": "env_api_key"}):
            adapter = LLMCommandAdapter(wake_word="xerife")
            assert adapter.api_key == "env_api_key"

    def test_initialization_without_api_key_raises_error(self, mock_genai):
        """Test that initialization without API key raises ValueError"""
        from app.adapters.infrastructure import LLMCommandAdapter

        with patch.dict(os.environ, {}, clear=True):
            # Clear GEMINI_API_KEY from environment
            os.environ.pop("GEMINI_API_KEY", None)

            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                LLMCommandAdapter(wake_word="xerife")

    def test_remove_wake_word(self, mock_genai):
        """Test that wake word is removed from input"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response with a function call
        mock_response = self._create_mock_function_response("type_text", {"text": "hello"})
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")
        adapter._interpret_sync("xerife escreva hello")

        # Check that the message sent to the model doesn't include the wake word
        # The send_message should be called with "escreva hello"
        mock_chat.send_message.assert_called_once()
        call_args = mock_chat.send_message.call_args[0][0]
        assert "xerife" not in call_args.lower()
        assert "escreva" in call_args.lower()

    def test_convert_function_call_type_text(self, mock_genai, mock_voice_provider):
        """Test conversion of type_text function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response("type_text", {"text": "hello world"})
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("escreva hello world")

        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "hello world"
        assert intent.confidence == 0.9

    def test_convert_function_call_press_key(self, mock_genai, mock_voice_provider):
        """Test conversion of press_key function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response("press_key", {"key": "enter"})
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("aperte enter")

        assert intent.command_type == CommandType.PRESS_KEY
        assert intent.parameters["key"] == "enter"
        assert intent.confidence == 0.9

    def test_convert_function_call_open_browser(self, mock_genai, mock_voice_provider):
        """Test conversion of open_browser function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response("open_browser", {})
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("abra o navegador")

        assert intent.command_type == CommandType.OPEN_BROWSER
        assert intent.parameters == {}
        assert intent.confidence == 0.9

    def test_convert_function_call_open_url(self, mock_genai, mock_voice_provider):
        """Test conversion of open_url function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response("open_url", {"url": "google.com"})
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("abra o google")

        assert intent.command_type == CommandType.OPEN_URL
        assert intent.parameters["url"] == "https://google.com"
        assert intent.confidence == 0.9

    def test_convert_function_call_search_on_page(self, mock_genai, mock_voice_provider):
        """Test conversion of search_on_page function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response(
            "search_on_page", {"search_text": "login"}
        )
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("procure login")

        assert intent.command_type == CommandType.SEARCH_ON_PAGE
        assert intent.parameters["search_text"] == "login"
        assert intent.confidence == 0.9

    def test_clarification_request(self, mock_genai, mock_voice_provider):
        """Test handling of clarification requests from LLM"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response with text (clarification)
        mock_response = self._create_mock_text_response("O que você gostaria que eu fizesse?")
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("faça algo")

        assert intent.command_type == CommandType.UNKNOWN
        assert "clarification" in intent.parameters
        assert intent.confidence == 0.3
        mock_voice_provider.speak.assert_called_once_with("O que você gostaria que eu fizesse?")

    def test_unknown_command(self, mock_genai, mock_voice_provider):
        """Test handling of unknown commands"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock the response with no function call
        mock_response = Mock()
        mock_response.candidates = []
        mock_chat.send_message = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("comando desconhecido")

        assert intent.command_type == CommandType.UNKNOWN
        assert intent.confidence == 0.5

    def test_error_handling(self, mock_genai, mock_voice_provider):
        """Test error handling during interpretation"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_model, mock_chat = mock_genai

        # Mock an exception
        mock_chat.send_message = Mock(side_effect=Exception("API Error"))

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("escreva teste")

        assert intent.command_type == CommandType.UNKNOWN
        assert "error" in intent.parameters
        assert intent.confidence == 0.0

    def test_is_exit_command(self, mock_genai):
        """Test exit command detection"""
        from app.adapters.infrastructure import LLMCommandAdapter

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")

        assert adapter.is_exit_command("fechar") is True
        assert adapter.is_exit_command("sair") is True
        assert adapter.is_exit_command("encerrar") is True
        assert adapter.is_exit_command("tchau") is True
        assert adapter.is_exit_command("escreva algo") is False

    def test_is_cancel_command(self, mock_genai):
        """Test cancel command detection"""
        from app.adapters.infrastructure import LLMCommandAdapter

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")

        assert adapter.is_cancel_command("cancelar") is True
        assert adapter.is_cancel_command("parar") is True
        assert adapter.is_cancel_command("stop") is True
        assert adapter.is_cancel_command("escreva algo") is False

    def _create_mock_function_response(self, function_name: str, args: dict):
        """Helper to create a mock response with a function call"""
        mock_response = Mock()
        mock_candidate = Mock()
        mock_content = Mock()
        mock_part = Mock()

        # Set up the function call
        mock_function_call = Mock()
        mock_function_call.name = function_name
        mock_function_call.args = args

        mock_part.function_call = mock_function_call
        mock_content.parts = [mock_part]
        mock_candidate.content = mock_content
        mock_response.candidates = [mock_candidate]

        return mock_response

    def _create_mock_text_response(self, text: str):
        """Helper to create a mock response with text"""
        mock_response = Mock()
        mock_candidate = Mock()
        mock_content = Mock()
        mock_part = Mock()

        # Set up the text response
        mock_part.text = text
        mock_part.function_call = None
        mock_content.parts = [mock_part]
        mock_candidate.content = mock_content
        mock_response.candidates = [mock_candidate]

        return mock_response
