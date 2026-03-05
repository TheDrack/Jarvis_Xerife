# -*- coding: utf-8 -*-
"""Tests for OllamaAdapter — LLMs locais via Ollama."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.infrastructure.ollama_adapter import OllamaAdapter


class TestOllamaAdapterInit:
    """Testa inicialização com defaults e com valores customizados."""

    def test_default_model(self):
        adapter = OllamaAdapter()
        assert adapter.model == "qwen2.5-coder:7b"

    def test_default_base_url(self):
        adapter = OllamaAdapter()
        assert adapter.base_url == "http://localhost:11434"

    def test_custom_model_and_url(self):
        adapter = OllamaAdapter(model="qwen2.5:14b", base_url="http://localhost:11434/")
        assert adapter.model == "qwen2.5:14b"
        assert adapter.base_url == "http://localhost:11434"  # trailing slash stripped

    def test_available_starts_as_none(self):
        adapter = OllamaAdapter()
        assert adapter._available is None


class TestOllamaAdapterExecute:
    """Testa o método execute()."""

    def test_execute_sem_prompt_retorna_success_false(self):
        adapter = OllamaAdapter()
        result = adapter.execute({})
        assert result["success"] is False
        assert "prompt" in result["error"].lower()

    def test_execute_com_prompt_vazio_retorna_success_false(self):
        adapter = OllamaAdapter()
        result = adapter.execute({"prompt": ""})
        assert result["success"] is False

    def test_execute_com_prompt_valido_retorna_success_true(self):
        adapter = OllamaAdapter()
        with patch.object(adapter, "_chat", return_value='{"resposta": "ok"}'):
            result = adapter.execute({"prompt": "Olá, Jarvis!"})

        assert result["success"] is True
        assert result["response"] == '{"resposta": "ok"}'
        assert result["provider"] == "ollama"
        assert result["model"] == "qwen2.5-coder:7b"

    def test_execute_usa_model_do_context(self):
        adapter = OllamaAdapter()
        with patch.object(adapter, "_chat", return_value="{}") as mock_chat:
            result = adapter.execute({"prompt": "test", "model": "deepseek-r1:8b"})

        assert result["model"] == "deepseek-r1:8b"
        mock_chat.assert_called_once_with("test", "deepseek-r1:8b", True, None)

    def test_execute_retorna_success_false_quando_chat_falha(self):
        adapter = OllamaAdapter()
        with patch.object(adapter, "_chat", side_effect=Exception("connection refused")):
            result = adapter.execute({"prompt": "test"})

        assert result["success"] is False
        assert "connection refused" in result["error"]
        assert result["provider"] == "ollama"


class TestOllamaAdapterIsAvailable:
    """Testa o método is_available()."""

    def test_is_available_retorna_false_quando_ollama_inacessivel(self):
        adapter = OllamaAdapter()
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            result = adapter.is_available()

        assert result is False
        assert adapter._available is False

    def test_is_available_retorna_true_quando_ollama_acessivel(self):
        adapter = OllamaAdapter()
        mock_resp = MagicMock()
        mock_resp.status = 200
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.is_available()

        assert result is True
        assert adapter._available is True

    def test_is_available_usa_cache_apos_primeira_chamada(self):
        adapter = OllamaAdapter()
        adapter._available = False
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = adapter.is_available()

        mock_urlopen.assert_not_called()
        assert result is False


class TestOllamaAdapterListLocalModels:
    """Testa list_local_models()."""

    def test_list_local_models_retorna_lista_vazia_quando_inacessivel(self):
        adapter = OllamaAdapter()
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            result = adapter.list_local_models()

        assert result == []

    def test_list_local_models_retorna_nomes_dos_modelos(self):
        adapter = OllamaAdapter()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"models": [{"name": "qwen2.5-coder:7b"}, {"name": "deepseek-r1:8b"}]}
        ).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.list_local_models()

        assert "qwen2.5-coder:7b" in result
        assert "deepseek-r1:8b" in result
