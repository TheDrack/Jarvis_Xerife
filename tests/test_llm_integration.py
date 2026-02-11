# -*- coding: utf-8 -*-
"""Tests for LLM-based command interpretation and capability detection"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.domain.models import CommandType, Intent
from app.domain.services.llm_command_interpreter import LLMCommandInterpreter
from app.application.services.llm_capability_detector import LLMCapabilityDetector
from app.core.llm_config import LLMConfig, create_command_interpreter


class TestLLMCommandInterpreter:
    """Tests for LLM-based command interpreter"""
    
    @pytest.fixture
    def mock_ai_gateway(self):
        """Create a mock AI Gateway"""
        gateway = MagicMock()
        gateway.generate_completion = AsyncMock()
        return gateway
    
    @pytest.fixture
    def interpreter(self, mock_ai_gateway):
        """Create LLM command interpreter with mock gateway"""
        return LLMCommandInterpreter(wake_word="xerife", ai_gateway=mock_ai_gateway)
    
    @pytest.mark.asyncio
    async def test_llm_interpret_type_text_command(self, interpreter, mock_ai_gateway):
        """Test LLM interpretation of type text command"""
        # Mock LLM response
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"command_type": "TYPE_TEXT", "parameters": {"text": "hello world"}, "confidence": 0.95, "reasoning": "User wants to type text"}'
                        )
                    )
                ]
            )
        }
        mock_ai_gateway.generate_completion.return_value = mock_response
        
        # Test interpretation
        intent = await interpreter.interpret_async("xerife escreva hello world")
        
        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "hello world"
        assert intent.confidence >= 0.9
        assert mock_ai_gateway.generate_completion.called
    
    @pytest.mark.asyncio
    async def test_llm_interpret_press_key_command(self, interpreter, mock_ai_gateway):
        """Test LLM interpretation of press key command"""
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"command_type": "PRESS_KEY", "parameters": {"key": "enter"}, "confidence": 0.92, "reasoning": "User wants to press enter key"}'
                        )
                    )
                ]
            )
        }
        mock_ai_gateway.generate_completion.return_value = mock_response
        
        intent = await interpreter.interpret_async("aperte enter")
        
        assert intent.command_type == CommandType.PRESS_KEY
        assert intent.parameters["key"] == "enter"
        assert intent.confidence >= 0.9
    
    @pytest.mark.asyncio
    async def test_llm_low_confidence_uses_fallback(self, interpreter, mock_ai_gateway):
        """Test low confidence response falls back to keyword interpretation"""
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"command_type": "TYPE_TEXT", "parameters": {"text": "ignored"}, "confidence": 0.2, "reasoning": "Low confidence"}'
                        )
                    )
                ]
            )
        }
        mock_ai_gateway.generate_completion.return_value = mock_response
        
        intent = await interpreter.interpret_async("xerife escreva teste")
        
        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "teste"
        assert intent.confidence == 1.0
    
    @pytest.mark.asyncio
    async def test_llm_interpret_fallback_on_error(self, interpreter, mock_ai_gateway):
        """Test fallback to keyword-based when LLM fails"""
        # Make LLM fail
        mock_ai_gateway.generate_completion.side_effect = Exception("LLM error")
        
        # Should fallback to keyword-based interpretation
        intent = await interpreter.interpret_async("xerife escreva teste")
        
        # Should still work via fallback
        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters.get("text") == "teste"
    
    def test_synchronous_interpret_uses_fallback(self, interpreter):
        """Test that synchronous interpret uses fallback"""
        intent = interpreter.interpret("xerife escreva hello")
        
        # Should use fallback (keyword-based)
        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters.get("text") == "hello"
    
    def test_is_exit_command(self, interpreter):
        """Test exit command detection"""
        assert interpreter.is_exit_command("fechar")
        assert interpreter.is_exit_command("sair")
        assert not interpreter.is_exit_command("escreva algo")
    
    def test_is_cancel_command(self, interpreter):
        """Test cancel command detection"""
        assert interpreter.is_cancel_command("cancelar")
        assert interpreter.is_cancel_command("parar")
        assert not interpreter.is_cancel_command("escreva algo")


class TestLLMCapabilityDetector:
    """Tests for LLM-based capability detector"""
    
    @pytest.fixture
    def mock_ai_gateway(self):
        """Create a mock AI Gateway"""
        gateway = MagicMock()
        gateway.generate_completion = AsyncMock()
        return gateway
    
    @pytest.fixture
    def detector(self, mock_ai_gateway, tmp_path):
        """Create LLM capability detector with mock gateway"""
        return LLMCapabilityDetector(
            ai_gateway=mock_ai_gateway,
            repository_root=tmp_path
        )
    
    @pytest.mark.asyncio
    async def test_detect_complete_capability(self, detector, mock_ai_gateway):
        """Test detection of a complete capability"""
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"status": "complete", "confidence": 0.95, "evidence": ["Found implementation"], "files_found": ["test.py"], "recommendations": []}'
                        )
                    )
                ]
            )
        }
        mock_ai_gateway.generate_completion.return_value = mock_response
        
        result = await detector.detect_capability_async(
            capability_id=1,
            capability_name="Test Capability",
            capability_description="A test capability"
        )
        
        assert result["status"] == "complete"
        assert result["confidence"] >= 0.9
        assert len(result["evidence"]) > 0
    
    @pytest.mark.asyncio
    async def test_detect_partial_capability(self, detector, mock_ai_gateway):
        """Test detection of a partial capability"""
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"status": "partial", "confidence": 0.85, "evidence": ["Found partial implementation"], "files_found": ["partial.py"], "recommendations": ["Add tests"]}'
                        )
                    )
                ]
            )
        }
        mock_ai_gateway.generate_completion.return_value = mock_response
        
        result = await detector.detect_capability_async(
            capability_id=2,
            capability_name="Partial Capability",
            capability_description="A partially implemented capability"
        )
        
        assert result["status"] == "partial"
        assert result["confidence"] >= 0.8
        assert len(result["recommendations"]) > 0
    
    @pytest.mark.asyncio
    async def test_fallback_on_error(self, detector, mock_ai_gateway):
        """Test fallback when LLM fails"""
        mock_ai_gateway.generate_completion.side_effect = Exception("LLM error")
        
        result = await detector.detect_capability_async(
            capability_id=3,
            capability_name="Error Capability",
            capability_description="Should trigger fallback"
        )
        
        # Should return fallback response
        assert result["status"] == "nonexistent"
        assert result["confidence"] < 0.5
        assert "LLM analysis not available" in result["evidence"][0]


class TestLLMConfig:
    """Tests for LLM configuration"""
    
    def test_config_validation(self):
        """Test configuration validation"""
        assert LLMConfig.validate_config()
    
    def test_config_summary(self):
        """Test configuration summary"""
        summary = LLMConfig.get_config_summary()
        
        assert "llm_command_interpretation" in summary
        assert "llm_capability_detection" in summary
        assert "copilot_context_generation" in summary
        assert isinstance(summary["min_command_confidence"], float)
    
    @patch.dict('os.environ', {'JARVIS_USE_LLM_COMMANDS': 'false'})
    def test_create_interpreter_without_llm(self):
        """Test creating interpreter when LLM is disabled"""
        from app.core.llm_config import create_command_interpreter
        
        # Reload the config to pick up the env var change
        import importlib
        import app.core.llm_config
        importlib.reload(app.core.llm_config)
        
        interpreter = app.core.llm_config.create_command_interpreter()
        
        # Should create keyword-based interpreter
        from app.domain.services.command_interpreter import CommandInterpreter
        assert isinstance(interpreter, CommandInterpreter)
    
    def test_create_interpreter_with_llm(self):
        """Test creating interpreter when LLM is enabled"""
        mock_gateway = MagicMock()
        
        # Create interpreter with gateway provided
        from app.core.llm_config import create_command_interpreter
        interpreter = create_command_interpreter(ai_gateway=mock_gateway)
        
        # Should create LLM-based interpreter when:
        # 1. LLM is enabled in config (default), AND
        # 2. Gateway is provided (which we did)
        from app.domain.services.llm_command_interpreter import LLMCommandInterpreter
        from app.domain.services.command_interpreter import CommandInterpreter
        from app.core.llm_config import LLMConfig
        
        if LLMConfig.USE_LLM_COMMAND_INTERPRETATION:
            # If LLM is enabled, should get LLM interpreter
            assert isinstance(interpreter, LLMCommandInterpreter)
        else:
            # If LLM is disabled, should get standard interpreter
            assert isinstance(interpreter, CommandInterpreter)


class TestIntegration:
    """Integration tests for LLM-based systems"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_command_interpretation(self):
        """Test end-to-end command interpretation with real AI Gateway (if available)"""
        # This test would require real API keys, so we'll mock it
        mock_gateway = MagicMock()
        mock_gateway.generate_completion = AsyncMock()
        
        mock_response = {
            "provider": "groq",
            "response": MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"command_type": "OPEN_URL", "parameters": {"url": "https://google.com"}, "confidence": 0.98, "reasoning": "User wants to open Google"}'
                        )
                    )
                ]
            )
        }
        mock_gateway.generate_completion.return_value = mock_response
        
        interpreter = LLMCommandInterpreter(wake_word="jarvis", ai_gateway=mock_gateway)
        intent = await interpreter.interpret_async("jarvis abra o google")
        
        assert intent.command_type == CommandType.OPEN_URL
        assert "google" in intent.parameters.get("url", "").lower()
        assert intent.confidence >= 0.9
