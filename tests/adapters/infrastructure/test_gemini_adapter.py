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
        """Mock google.genai module for new SDK"""
        with patch("app.adapters.infrastructure.gemini_adapter.genai") as mock:
            # Mock the Client class
            mock_client = Mock()
            mock.Client = Mock(return_value=mock_client)

            # Mock the types module
            mock_types = Mock()
            mock.types = mock_types
            mock_types.Tool = Mock()
            mock_types.GenerateContentConfig = Mock()

            # Mock the client's models.generate_content method
            mock_client.models = Mock()
            mock_client.models.generate_content = Mock()

            yield mock, mock_client

    @pytest.fixture
    def mock_voice_provider(self):
        """Mock VoiceProvider"""
        voice = Mock()
        voice.speak = Mock()
        return voice

    def test_initialization_with_api_key(self, mock_genai):
        """Test LLMCommandAdapter initialization with API key"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        adapter = LLMCommandAdapter(api_key="test_api_key", wake_word="xerife")

        assert adapter.api_key == "test_api_key"
        assert adapter.wake_word == "xerife"
        assert adapter.model_name == "gemini-flash-latest"
        mock_genai_module.Client.assert_called_once_with(api_key="test_api_key")

    def test_initialization_from_env(self, mock_genai):
        """Test LLMCommandAdapter initialization from environment variable"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, _ = mock_genai

        with patch.dict(os.environ, {"GEMINI_API_KEY": "env_api_key"}):
            adapter = LLMCommandAdapter(wake_word="xerife")
            assert adapter.api_key == "env_api_key"

    def test_initialization_from_google_api_key_env(self, mock_genai):
        """Test LLMCommandAdapter initialization from GOOGLE_API_KEY environment variable"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, _ = mock_genai

        with patch.dict(
            os.environ, {"GOOGLE_API_KEY": "google_env_api_key"}, clear=True
        ):
            adapter = LLMCommandAdapter(wake_word="xerife")
            assert adapter.api_key == "google_env_api_key"

    def test_initialization_prefers_google_api_key_over_gemini(self, mock_genai):
        """Test that GOOGLE_API_KEY takes precedence over GEMINI_API_KEY"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, _ = mock_genai

        with patch.dict(
            os.environ,
            {"GOOGLE_API_KEY": "google_key", "GEMINI_API_KEY": "gemini_key"},
        ):
            adapter = LLMCommandAdapter(wake_word="xerife")
            assert adapter.api_key == "google_key"

    def test_initialization_without_api_key_raises_error(self, mock_genai):
        """Test that initialization without API key raises ValueError"""
        from app.adapters.infrastructure import LLMCommandAdapter

        with patch.dict(os.environ, {}, clear=True):
            # Clear both GEMINI_API_KEY and GOOGLE_API_KEY from environment
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)

            with pytest.raises(ValueError, match="GOOGLE_API_KEY or GEMINI_API_KEY"):
                LLMCommandAdapter(wake_word="xerife")

    def test_remove_wake_word(self, mock_genai):
        """Test that wake word is removed from input"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response with a function call
        mock_response = self._create_mock_function_response(
            "type_text", {"text": "hello"}
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")
        adapter._interpret_sync("xerife escreva hello")

        # Check that the message sent to the model doesn't include the wake word
        # The generate_content should be called with "escreva hello"
        mock_client.models.generate_content.assert_called_once()
        call_args = mock_client.models.generate_content.call_args
        contents_arg = call_args[1].get("contents") if call_args[1] else call_args[0][1]
        assert "xerife" not in contents_arg.lower()
        assert "escreva" in contents_arg.lower()

    def test_convert_function_call_type_text(self, mock_genai, mock_voice_provider):
        """Test conversion of type_text function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response(
            "type_text", {"text": "hello world"}
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

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

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response(
            "press_key", {"key": "enter"}
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

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

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response("open_browser", {})
        mock_client.models.generate_content = Mock(return_value=mock_response)

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

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response(
            "open_url", {"url": "google.com"}
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("abra o google")

        assert intent.command_type == CommandType.OPEN_URL
        assert intent.parameters["url"] == "https://google.com"
        assert intent.confidence == 0.9

    def test_convert_function_call_search_on_page(
        self, mock_genai, mock_voice_provider
    ):
        """Test conversion of search_on_page function call to Intent"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_function_response(
            "search_on_page", {"search_text": "login"}
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

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

        mock_genai_module, mock_client = mock_genai

        # Mock the response with text (clarification)
        mock_response = self._create_mock_text_response(
            "O que você gostaria que eu fizesse?"
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        intent = adapter._interpret_sync("faça algo")

        assert intent.command_type == CommandType.UNKNOWN
        assert "clarification" in intent.parameters
        assert intent.confidence == 0.3
        mock_voice_provider.speak.assert_called_once_with(
            "O que você gostaria que eu fizesse?"
        )

    def test_unknown_command(self, mock_genai, mock_voice_provider):
        """Test handling of unknown commands"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response with no function call
        mock_response = Mock()
        mock_response.candidates = []
        mock_client.models.generate_content = Mock(return_value=mock_response)

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

        mock_genai_module, mock_client = mock_genai

        # Mock an exception
        mock_client.models.generate_content = Mock(side_effect=Exception("API Error"))

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

    def test_generate_conversational_response(self, mock_genai, mock_voice_provider):
        """Test generating conversational responses for greetings/unknown commands"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response with conversational text
        mock_response = self._create_mock_text_response(
            "Olá! Como posso ajudar você hoje?"
        )
        mock_client.models.generate_content = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        response = adapter.generate_conversational_response("olá")

        assert response == "Olá! Como posso ajudar você hoje?"
        mock_client.models.generate_content.assert_called_once()

    def test_generate_conversational_response_removes_wake_word(
        self, mock_genai, mock_voice_provider
    ):
        """Test that conversational response removes wake word from input"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock the response
        mock_response = self._create_mock_text_response("Oi! Tudo bem?")
        mock_client.models.generate_content = Mock(return_value=mock_response)

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        response = adapter.generate_conversational_response("xerife olá")

        assert response == "Oi! Tudo bem?"
        # Check that wake word was removed from the prompt
        call_args = mock_client.models.generate_content.call_args
        contents_arg = call_args[1].get("contents") if call_args[1] else call_args[0][1]
        assert "xerife" not in contents_arg.lower()

    def test_generate_conversational_response_empty_input(
        self, mock_genai, mock_voice_provider
    ):
        """Test conversational response with empty input"""
        from app.adapters.infrastructure import LLMCommandAdapter

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        response = adapter.generate_conversational_response("")

        assert response == "Olá! Como posso ajudar?"

    def test_generate_conversational_response_error_handling(
        self, mock_genai, mock_voice_provider
    ):
        """Test error handling in conversational response generation"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock an exception
        mock_client.models.generate_content = Mock(side_effect=Exception("API Error"))

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )
        response = adapter.generate_conversational_response("olá")

        assert "Desculpe, ocorreu um erro" in response

    def test_503_error_handling_async(self, mock_genai, mock_voice_provider):
        """Test 503 error handling in async interpretation"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock a 503 error
        mock_client.models.generate_content = Mock(
            side_effect=Exception("503 Service Unavailable")
        )

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )

        # Mock the GitHub issue creation to avoid actual API calls
        with patch.object(
            adapter, "_create_github_issue_for_infra_failure_sync"
        ) as mock_create_issue:
            intent = adapter._interpret_sync("escreva teste")

            # Verify the error was logged as INFRA_FAILURE and GitHub issue was created
            mock_create_issue.assert_called_once()
            assert intent.command_type == CommandType.UNKNOWN
            assert "error" in intent.parameters
            assert "503" in intent.parameters["error"]

    def test_503_error_with_unavailable_in_message(
        self, mock_genai, mock_voice_provider
    ):
        """Test 503 error handling when error message contains UNAVAILABLE"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock an error with UNAVAILABLE in the message
        mock_client.models.generate_content = Mock(
            side_effect=Exception("Request failed: UNAVAILABLE")
        )

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )

        # Mock the GitHub issue creation
        with patch.object(
            adapter, "_create_github_issue_for_infra_failure_sync"
        ) as mock_create_issue:
            intent = adapter._interpret_sync("escreva teste")

            # Verify GitHub issue was created for UNAVAILABLE error
            mock_create_issue.assert_called_once()
            assert intent.command_type == CommandType.UNKNOWN

    def test_non_503_error_not_triggering_issue(self, mock_genai, mock_voice_provider):
        """Test that non-503 errors don't trigger GitHub issue creation"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        # Mock a non-503 error
        mock_client.models.generate_content = Mock(
            side_effect=Exception("Generic API Error")
        )

        adapter = LLMCommandAdapter(
            api_key="test_key",
            voice_provider=mock_voice_provider,
            wake_word="xerife",
        )

        # Mock the GitHub issue creation
        with patch.object(
            adapter, "_create_github_issue_for_infra_failure_sync"
        ) as mock_create_issue:
            intent = adapter._interpret_sync("escreva teste")

            # Verify GitHub issue was NOT created for non-503 error
            mock_create_issue.assert_not_called()
            assert intent.command_type == CommandType.UNKNOWN

    def test_github_issue_creation_without_token(self, mock_genai):
        """Test GitHub issue creation when GITHUB_TOKEN is not available"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")

        # Clear GITHUB_TOKEN from environment
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise an error, just log a warning
            adapter._create_github_issue_for_infra_failure_sync(
                Exception("503 error"), "Test error details"
            )
            # No assertion needed, just verify it doesn't crash

    def test_github_issue_creation_without_repository(self, mock_genai):
        """Test GitHub issue creation when GITHUB_REPOSITORY is not available"""
        from app.adapters.infrastructure import LLMCommandAdapter

        mock_genai_module, mock_client = mock_genai

        adapter = LLMCommandAdapter(api_key="test_key", wake_word="xerife")

        # Set GITHUB_TOKEN but clear GITHUB_REPOSITORY
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"}, clear=True):
            # Should not raise an error, just log a warning
            adapter._create_github_issue_for_infra_failure_sync(
                Exception("503 error"), "Test error details"
            )
            # No assertion needed, just verify it doesn't crash
