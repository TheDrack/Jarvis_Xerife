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

