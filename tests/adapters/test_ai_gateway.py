# -*- coding: utf-8 -*-
"""Tests for AI Gateway"""

from unittest.mock import Mock, patch

import pytest

# Check if tiktoken is available for tests
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider


class TestAIGateway:
    """Test cases for AI Gateway"""

    @pytest.fixture
    def mock_groq_client(self):
        """Create a mock Groq client"""
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "Test response from Groq"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    @pytest.fixture
    def mock_gemini_client(self):
        """Create a mock Gemini client"""
        mock_client = Mock()
        mock_response = Mock()
        mock_candidate = Mock()
        mock_part = Mock()
        mock_part.text = "Test response from Gemini"
        mock_candidate.content.parts = [mock_part]
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response
        return mock_client

    def test_gateway_initialization_with_keys(self):
        """Test that gateway initializes correctly with API keys"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        assert gateway.groq_api_key == "test_groq_key"
        assert gateway.gemini_api_key == "test_gemini_key"
        assert gateway.default_provider == LLMProvider.GROQ

    def test_gateway_initialization_without_keys(self):
        """Test that gateway handles missing API keys gracefully"""
        gateway = AIGateway(
            groq_api_key=None,
            gemini_api_key=None,
        )
        assert gateway.groq_client is None
        assert gateway.gemini_client is None

    def test_token_counting(self):
        """Test token counting functionality"""
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
        )
        
        # Test with a simple string
        text = "Hello, this is a test message."
        token_count = gateway.count_tokens(text)
        
        # Token count should be positive
        assert token_count > 0
        
        # Longer text should have more tokens
        longer_text = text * 100
        longer_count = gateway.count_tokens(longer_text)
        assert longer_count > token_count
        
        # With tiktoken, we expect more precise counting
        if HAS_TIKTOKEN:
            # The exact count may vary, but tokens typically <= characters
            assert token_count <= len(text)  # Tokens should not exceed characters
        else:
            # Without tiktoken, we use character approximation (len // 4)
            assert token_count == len(text) // 4

    def test_select_provider_default_groq(self):
        """Test that short payloads default to Groq"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Mock the clients to be available
        gateway.groq_client = Mock()
        gateway.gemini_client = Mock()
        
        # Short payload should select Groq
        short_payload = "This is a short message."
        provider = gateway.select_provider(short_payload)
        
        assert provider == LLMProvider.GROQ

    def test_select_provider_escalate_to_gemini_for_large_payload(self):
        """Test that large payloads escalate to Gemini"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Mock the clients to be available
        gateway.groq_client = Mock()
        gateway.gemini_client = Mock()
        
        # Create a large payload (simulate > 10k tokens)
        # Since tiktoken is not available in tests, use character count fallback
        # 1 token ≈ 4 characters, so 10k tokens ≈ 40k characters
        large_payload = "word " * 10000  # Approximately 50k characters = 12.5k tokens
        provider = gateway.select_provider(large_payload)
        
        assert provider == LLMProvider.GEMINI

    def test_select_provider_multimodal_requires_gemini(self):
        """Test that multimodal requests require Gemini"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Mock the clients to be available
        gateway.groq_client = Mock()
        gateway.gemini_client = Mock()
        
        # Multimodal should always select Gemini
        provider = gateway.select_provider("Any text", multimodal=True)
        
        assert provider == LLMProvider.GEMINI

    def test_select_provider_force_provider(self):
        """Test that force_provider overrides automatic selection"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Mock the clients to be available
        gateway.groq_client = Mock()
        gateway.gemini_client = Mock()
        
        # Force Gemini even for short payload
        provider = gateway.select_provider(
            "Short text",
            force_provider=LLMProvider.GEMINI
        )
        
        assert provider == LLMProvider.GEMINI

    def test_select_provider_no_providers_available(self):
        """Test error when no providers are available"""
        gateway = AIGateway(
            groq_api_key=None,
            gemini_api_key=None,
        )
        
        with pytest.raises(ValueError, match="No LLM providers available"):
            gateway.select_provider("Any text")

    def test_is_rate_limit_error(self):
        """Test detection of rate limit errors"""
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
        )
        
        # Test various rate limit error messages
        rate_limit_errors = [
            Exception("Rate limit exceeded"),
            Exception("Too many requests"),
            Exception("HTTP 429 error"),
            Exception("Quota exceeded"),
        ]
        
        for error in rate_limit_errors:
            assert gateway._is_rate_limit_error(error)
        
        # Non-rate-limit error
        other_error = Exception("Internal server error")
        assert not gateway._is_rate_limit_error(other_error)
    
    def test_is_model_decommissioned_error(self):
        """Test detection of model decommissioned errors"""
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
        )
        
        # Test various model decommissioned error messages
        decommissioned_errors = [
            Exception("model_decommissioned"),
            Exception("The model has been decommissioned"),
            Exception("Model has been deprecated and is no longer available"),
        ]
        
        for error in decommissioned_errors:
            assert gateway._is_model_decommissioned_error(error)
        
        # Non-decommissioned error
        other_error = Exception("Internal server error")
        assert not gateway._is_model_decommissioned_error(other_error)


    @pytest.mark.asyncio
    async def test_generate_with_groq(self, mock_groq_client):
        """Test generating completion with Groq"""
        # Create gateway without initialization to avoid import issues
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Directly set the mock client
        gateway.groq_client = mock_groq_client
        
        messages = [
            {"role": "user", "content": "Hello, how are you?"}
        ]
        
        result = await gateway._generate_with_groq(messages)
        
        assert result["provider"] == LLMProvider.GROQ.value
        assert "response" in result
        assert result["model"] == gateway.groq_model

    def test_convert_functions_to_groq_tools(self):
        """Test conversion of Gemini functions to Groq tools format"""
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
        )
        
        # Mock function declaration
        mock_func = Mock()
        mock_func.name = "test_function"
        mock_func.description = "A test function"
        mock_func.parameters = Mock()
        mock_func.parameters.properties = {
            "param1": Mock(type="string", description="First parameter")
        }
        mock_func.parameters.required = ["param1"]
        
        tools = gateway._convert_functions_to_groq_tools([mock_func])
        
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "test_function"
        assert tools[0]["function"]["description"] == "A test function"
        assert "parameters" in tools[0]["function"]


class TestAIGatewayFallback:
    """Test cases for AI Gateway fallback mechanism"""

    @pytest.fixture
    def gateway_with_mocks(self):
        """Create a gateway with mocked clients"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
        )
        
        # Mock successful Groq client
        gateway.groq_client = Mock()
        groq_response = Mock()
        groq_choice = Mock()
        groq_message = Mock()
        groq_message.content = "Response from Groq"
        groq_choice.message = groq_message
        groq_response.choices = [groq_choice]
        gateway.groq_client.chat.completions.create.return_value = groq_response
        
        # Mock successful Gemini client
        gateway.gemini_client = Mock()
        gemini_response = Mock()
        gemini_candidate = Mock()
        gemini_part = Mock()
        gemini_part.text = "Response from Gemini"
        gemini_candidate.content.parts = [gemini_part]
        gemini_response.candidates = [gemini_candidate]
        gateway.gemini_client.models.generate_content.return_value = gemini_response
        
        return gateway

    @pytest.mark.asyncio
    async def test_fallback_from_groq_to_gemini_on_rate_limit(self, gateway_with_mocks):
        """Test that Groq rate limit triggers fallback to Gemini"""
        gateway = gateway_with_mocks
        
        # Make Groq raise a rate limit error
        gateway.groq_client.chat.completions.create.side_effect = Exception(
            "Rate limit exceeded"
        )
        
        messages = [{"role": "user", "content": "Test message"}]
        
        result = await gateway.generate_completion(messages)
        
        # Should have fallen back to Gemini
        assert result["provider"] == LLMProvider.GEMINI.value
        assert "fallback_from" in result
        assert result["fallback_from"] == LLMProvider.GROQ.value

    @pytest.mark.asyncio
    async def test_fallback_from_gemini_to_groq_on_rate_limit(self, gateway_with_mocks):
        """Test that Gemini rate limit triggers fallback to Groq"""
        gateway = gateway_with_mocks
        
        # Make Gemini raise a rate limit error
        gateway.gemini_client.models.generate_content.side_effect = Exception(
            "Quota exceeded"
        )
        
        # Create a large payload to force Gemini selection
        # 1 token ≈ 4 characters, so 10k tokens ≈ 40k characters
        large_payload = "word " * 10000  # Approximately 50k characters = 12.5k tokens
        messages = [{"role": "user", "content": large_payload}]
        
        result = await gateway.generate_completion(messages)
        
        # Should have fallen back to Groq
        assert result["provider"] == LLMProvider.GROQ.value
        assert "fallback_from" in result
        assert result["fallback_from"] == LLMProvider.GEMINI.value

    @pytest.mark.asyncio
    async def test_no_fallback_available_raises_error(self):
        """Test that error is raised when no fallback is available"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key=None,  # No Gemini available
        )
        
        # Mock Groq to raise rate limit error
        gateway.groq_client = Mock()
        gateway.groq_client.chat.completions.create.side_effect = Exception(
            "Rate limit exceeded"
        )
        
        messages = [{"role": "user", "content": "Test"}]
        
        with pytest.raises(ValueError, match="no fallback provider available"):
            await gateway.generate_completion(messages)
    
    @pytest.mark.asyncio
    async def test_model_decommissioned_error_with_fallback(self, gateway_with_mocks):
        """Test that model decommissioned error triggers fallback to Gemini"""
        gateway = gateway_with_mocks
        
        # Make Groq raise a model decommissioned error
        gateway.groq_client.chat.completions.create.side_effect = Exception(
            "model_decommissioned: The model llama-3.1-70b-versatile has been decommissioned"
        )
        
        messages = [{"role": "user", "content": "Test message"}]
        
        result = await gateway.generate_completion(messages)
        
        # Should have fallen back to Gemini
        assert result["provider"] == LLMProvider.GEMINI.value
        assert "fallback_from" in result
        assert result["fallback_from"] == LLMProvider.GROQ.value
    
    @pytest.mark.asyncio
    async def test_model_decommissioned_error_without_fallback_raises_error(self):
        """Test that model decommissioned error without fallback raises informative error"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key=None,  # No Gemini available for fallback
            groq_model="llama-3.1-70b-versatile",
        )
        
        # Mock Groq to raise model decommissioned error
        gateway.groq_client = Mock()
        gateway.groq_client.chat.completions.create.side_effect = Exception(
            "model_decommissioned: Model has been deprecated"
        )
        
        messages = [{"role": "user", "content": "Test"}]
        
        with pytest.raises(ValueError) as exc_info:
            await gateway.generate_completion(messages)
        
        # Check that the error message contains helpful information
        error_message = str(exc_info.value)
        assert "llama-3.1-70b-versatile" in error_message
        assert "descomissionado" in error_message
        assert ".env" in error_message
        assert "llama-3.3-70b-versatile" in error_message
