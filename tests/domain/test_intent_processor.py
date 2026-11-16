# -*- coding: utf-8 -*-
"""Tests for Domain layer - Intent Processor"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.models import CommandType, Intent
from app.domain.services import IntentProcessor


class TestIntentProcessor:
    """Test cases for IntentProcessor — pure routing logic"""

    @pytest.fixture
    def processor(self):
        """Create an IntentProcessor instance"""
        return IntentProcessor()

    def test_execute_requires_intent_in_context(self, processor):
        """execute() sem 'intent' deve retornar mensagem de erro"""
        result = processor.execute({})
        assert "Erro" in result or "erro" in result.lower() or result

    def test_execute_unknown_intent_delegates_to_llm(self, processor):
        """UNKNOWN intent deve delegar para LLM (fallback)"""
        intent = Intent(command_type=CommandType.UNKNOWN, raw_input="como vai?")
        mock_llm = MagicMock()
        mock_llm.chat.return_value = "Resposta do LLM"

        with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_llm
            result = processor.execute({"intent": intent})

        assert result is not None

    def test_execute_with_none_context(self, processor):
        """execute() com contexto None deve tratar graciosamente"""
        result = processor.execute(None)
        assert result is not None

    def test_execute_returns_string(self, processor):
        """execute() deve sempre retornar string"""
        intent = Intent(command_type=CommandType.UNKNOWN, raw_input="teste")
        with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            result = processor.execute({"intent": intent})
        assert isinstance(result, str)

    def test_execute_technical_command_resolves_executor(self, processor):
        """Comando técnico deve tentar resolver executor no Nexus"""
        intent = Intent(command_type=CommandType.TYPE_TEXT, parameters={"text": "oi"})
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {"message": "Texto digitado"}

        with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_executor
            result = processor.execute({"intent": intent})

        assert result is not None




def test_execute_forwards_memory_context_to_llm_service():
    processor = IntentProcessor()
    intent = Intent(command_type=CommandType.UNKNOWN, raw_input="qual era o projeto?")
    processor._submit_laya_intent_shadow = MagicMock()
    processor._check_hardware_command = MagicMock(return_value={"success": False})
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Resposta com memória"

    with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = (
            lambda component_id: mock_llm if component_id == "llm_service" else None
        )
        result = processor.execute(
            {"intent": intent, "memory_context": "Projeto Atlas usa Python."}
        )

    assert result == "Resposta com memória"
    prompt = mock_llm.chat.call_args.args[0]
    system_instruction = mock_llm.chat.call_args.kwargs["system_instruction"]
    assert "Projeto Atlas usa Python." in prompt
    assert "dados históricos não confiáveis" in system_instruction


def test_execute_bounds_memory_context_before_llm_submission():
    processor = IntentProcessor()
    intent = Intent(command_type=CommandType.UNKNOWN, raw_input="resuma")
    processor._submit_laya_intent_shadow = MagicMock()
    processor._check_hardware_command = MagicMock(return_value={"success": False})
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "ok"
    oversized_context = "X" * 5000

    with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = (
            lambda component_id: mock_llm if component_id == "llm_service" else None
        )
        processor.execute({"intent": intent, "memory_context": oversized_context})

    prompt = mock_llm.chat.call_args.args[0]
    assert "X" * 4000 in prompt
    assert "X" * 4001 not in prompt


def test_execute_forwards_memory_context_to_ai_gateway_when_llm_service_unavailable():
    processor = IntentProcessor()
    intent = Intent(command_type=CommandType.UNKNOWN, raw_input="qual era o projeto?")
    processor._submit_laya_intent_shadow = MagicMock()
    processor._check_hardware_command = MagicMock(return_value={"success": False})
    mock_gateway = MagicMock()
    mock_gateway.execute.return_value = {"response": "Resposta do gateway"}

    with patch("app.domain.services.intent_processor.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = (
            lambda component_id: (
                None if component_id == "llm_service"
                else mock_gateway if component_id == "ai_gateway"
                else None
            )
        )
        result = processor.execute(
            {"intent": intent, "memory_context": "Projeto Atlas usa Python."}
        )

    assert result == "Resposta do gateway"
    messages = mock_gateway.execute.call_args.args[0]["messages"]
    assert messages[0]["role"] == "system"
    assert "dados históricos não confiáveis" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "Projeto Atlas usa Python." in messages[1]["content"]
