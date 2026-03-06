# -*- coding: utf-8 -*-
"""Tests for LLMRouter — seleção dinâmica de adaptador LLM por tarefa."""

from unittest.mock import MagicMock, patch

import pytest

from app.application.services.llm_router import LLMRouter, _adapter_name_to_model


class TestLLMRouterSelection:
    """Testa a seleção correta de adaptador por task_type."""

    def _make_router(self, available_adapters=None):
        """Cria um router com adaptadores mockados."""
        router = LLMRouter(reliability_threshold=0.6, default_adapter="metabolism_core")
        return router

    def _mock_nexus(self, router, adapters: dict):
        """Mocka nexus.resolve para retornar adaptadores fake."""
        def _resolve(name):
            return adapters.get(name)
        router._resolve_adapter = lambda name: adapters.get(name)
        return router

    def test_code_repair_selects_ollama(self):
        """code_repair e code_generation devem preferir OllamaAdapter."""
        ollama = MagicMock()
        ollama.is_available.return_value = True

        router = LLMRouter()
        router._resolve_adapter = lambda name: ollama if name == "ollama_adapter" else None

        adapter = router.select_adapter("code_repair")
        assert adapter is ollama

    def test_code_generation_selects_ollama(self):
        """code_generation deve preferir OllamaAdapter."""
        ollama = MagicMock()
        ollama.is_available.return_value = True

        router = LLMRouter()
        router._resolve_adapter = lambda name: ollama if name == "ollama_adapter" else None

        adapter = router.select_adapter("code_generation")
        assert adapter is ollama

    def test_planning_selects_metabolism_core(self):
        """planning deve selecionar metabolism_core."""
        metabolism = MagicMock()

        router = LLMRouter()
        router._resolve_adapter = lambda name: metabolism if name == "metabolism_core" else None

        adapter = router.select_adapter("planning")
        assert adapter is metabolism

    def test_evolution_selects_metabolism_core(self):
        """evolution deve selecionar metabolism_core."""
        metabolism = MagicMock()

        router = LLMRouter()
        router._resolve_adapter = lambda name: metabolism if name == "metabolism_core" else None

        adapter = router.select_adapter("evolution")
        assert adapter is metabolism

    def test_vision_selects_vision_adapter(self):
        """vision deve selecionar vision_adapter."""
        vision = MagicMock()

        router = LLMRouter()
        router._resolve_adapter = lambda name: vision if name == "vision_adapter" else None

        adapter = router.select_adapter("vision")
        assert adapter is vision

    def test_unknown_task_uses_default_adapter(self):
        """Task desconhecido deve usar o adaptador padrão configurado."""
        default = MagicMock()

        router = LLMRouter(default_adapter="metabolism_core")
        router._resolve_adapter = lambda name: default if name == "metabolism_core" else None

        adapter = router.select_adapter("some_unknown_task")
        assert adapter is default

    def test_no_adapter_returns_none(self):
        """Quando nenhum adaptador está disponível, retorna None."""
        router = LLMRouter(default_adapter="metabolism_core")
        router._resolve_adapter = lambda name: None

        adapter = router.select_adapter("code_repair")
        assert adapter is None


class TestLLMRouterFallback:
    """Testa fallback quando confiabilidade está baixa ou adaptador indisponível."""

    def test_fallback_when_ollama_unavailable(self):
        """Quando OllamaAdapter não está disponível, deve tentar o próximo."""
        ollama = MagicMock()
        ollama.is_available.return_value = False
        fallback = MagicMock()

        def _resolve(name):
            if name == "ollama_adapter":
                return ollama
            if name == "metabolism_core":
                return fallback
            return None

        router = LLMRouter(default_adapter="metabolism_core")
        router._resolve_adapter = _resolve

        adapter = router.select_adapter("code_repair")
        # Ollama indisponível → fallback para metabolism_core
        assert adapter is fallback

    def test_fallback_when_reliability_low(self):
        """Quando confiabilidade está abaixo do threshold, pula para o próximo."""
        ollama = MagicMock()
        ollama.is_available.return_value = True
        fallback = MagicMock()

        def _resolve(name):
            if name == "ollama_adapter":
                return ollama
            if name == "metabolism_core":
                return fallback
            return None

        router = LLMRouter(reliability_threshold=0.6, default_adapter="metabolism_core")
        # Força confiabilidade baixa para o ollama
        router._is_reliable = lambda name: name != "ollama_adapter"
        router._resolve_adapter = _resolve

        adapter = router.select_adapter("code_repair")
        assert adapter is fallback

    def test_execute_returns_error_when_no_adapter(self):
        """execute() deve retornar error se nenhum adaptador disponível."""
        router = LLMRouter()
        router._resolve_adapter = lambda name: None

        result = router.execute({"task_type": "vision", "prompt": "teste"})
        assert result["success"] is False
        assert "no_adapter_available" in result["error"]

    def test_execute_routes_to_adapter(self):
        """execute() deve chamar o adaptador selecionado."""
        adapter_mock = MagicMock()
        adapter_mock.execute.return_value = {"success": True, "response": "ok"}

        router = LLMRouter()
        router._resolve_adapter = lambda name: adapter_mock
        router._is_reliable = lambda name: True
        router._is_available = lambda adapter: True

        result = router.execute({"task_type": "planning", "prompt": "planejar algo"})
        assert result["success"] is True
        assert "routed_to" in result
        adapter_mock.execute.assert_called_once()


class TestLLMRouterHelpers:
    """Testa helpers internos do LLMRouter."""

    def test_adapter_name_to_model(self):
        """_adapter_name_to_model deve retornar o modelo correto."""
        assert _adapter_name_to_model("ollama_adapter") == "qwen2.5-coder:14b"
        assert _adapter_name_to_model("metabolism_core") == "groq/llama-3.3-70b-versatile"
        assert _adapter_name_to_model("vision_adapter") == "gemini-2.0-flash"
        assert _adapter_name_to_model("unknown") == ""

    def test_configure(self):
        """configure() deve atualizar os parâmetros do router."""
        router = LLMRouter()
        router.configure({"reliability_threshold": 0.8, "default_adapter": "ollama_adapter"})
        assert router.reliability_threshold == 0.8
        assert router.default_adapter == "ollama_adapter"

    def test_can_execute_true_when_adapter_available(self):
        """can_execute() deve retornar True quando há um adaptador."""
        adapter_mock = MagicMock()
        router = LLMRouter()
        router._resolve_adapter = lambda name: adapter_mock
        router._is_reliable = lambda name: True
        router._is_available = lambda adapter: True

        assert router.can_execute({"task_type": "planning"}) is True

    def test_can_execute_false_when_no_adapter(self):
        """can_execute() deve retornar False quando não há adaptadores."""
        router = LLMRouter()
        router._resolve_adapter = lambda name: None

        assert router.can_execute({"task_type": "planning"}) is False
