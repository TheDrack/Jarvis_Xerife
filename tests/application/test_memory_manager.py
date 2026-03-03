# -*- coding: utf-8 -*-
"""Tests for MemoryManager – long-term semantic memory service."""

import json
import os
import pytest

from app.application.services.memory_manager import MemoryManager


@pytest.fixture
def memory_manager(tmp_path):
    """MemoryManager apontando para um arquivo temporário."""
    storage = str(tmp_path / "test_memory.json")
    return MemoryManager(storage_path=storage, max_interactions=10)


class TestMemoryManagerStorageAndRetrieval:
    def test_store_and_load_interaction(self, memory_manager, tmp_path):
        """Deve persistir interação e recarregá-la do disco."""
        memory_manager.store_interaction("qual é a temperatura?", "Está 25°C lá fora.")
        data = json.loads((tmp_path / "test_memory.json").read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["user"] == "qual é a temperatura?"
        assert data[0]["jarvis"] == "Está 25°C lá fora."
        assert "timestamp" in data[0]

    def test_multiple_interactions_are_accumulated(self, memory_manager):
        """Deve acumular múltiplas interações."""
        memory_manager.store_interaction("pergunta 1", "resposta 1")
        memory_manager.store_interaction("pergunta 2", "resposta 2")
        memory_manager.store_interaction("pergunta 3", "resposta 3")
        ctx = memory_manager._load_interactions()
        assert len(ctx) == 3

    def test_max_interactions_limit_is_respected(self, tmp_path):
        """Não deve exceder max_interactions."""
        mm = MemoryManager(storage_path=str(tmp_path / "mem.json"), max_interactions=3)
        for i in range(5):
            mm.store_interaction(f"pergunta {i}", f"resposta {i}")
        data = mm._load_interactions()
        assert len(data) == 3
        # Deve manter as mais recentes
        assert data[0]["user"] == "pergunta 2"
        assert data[-1]["user"] == "pergunta 4"

    def test_load_returns_empty_list_when_file_missing(self, memory_manager):
        """Deve retornar lista vazia quando o arquivo não existe."""
        assert memory_manager._load_interactions() == []

    def test_load_returns_empty_list_on_corrupt_file(self, tmp_path):
        """Deve retornar lista vazia se o arquivo JSON estiver corrompido."""
        storage = tmp_path / "bad_memory.json"
        storage.write_text("not valid json", encoding="utf-8")
        mm = MemoryManager(storage_path=str(storage))
        assert mm._load_interactions() == []


class TestMemoryManagerRelevantContext:
    def test_get_relevant_context_matches_keywords(self, memory_manager):
        """Deve retornar interações com palavras-chave em comum."""
        memory_manager.store_interaction("como está o clima hoje?", "Está ensolarado.")
        memory_manager.store_interaction("qual é a previsão do tempo?", "Chuva amanhã.")
        memory_manager.store_interaction("me fale sobre python", "Python é uma linguagem.")
        result = memory_manager.get_relevant_context("clima tempo previsão")
        texts = [r["user"] for r in result]
        assert any("clima" in t for t in texts)
        assert any("previsão" in t or "tempo" in t for t in texts)

    def test_get_relevant_context_ignores_short_words(self, memory_manager):
        """Palavras com 2 ou menos caracteres não devem ser usadas como keywords."""
        memory_manager.store_interaction("ok vai", "certo")
        # Query com apenas palavras curtas não deve retornar resultados por keyword match
        result = memory_manager.get_relevant_context("ok")
        assert result == []

    def test_get_relevant_context_empty_query(self, memory_manager):
        """Query vazia deve retornar lista vazia."""
        memory_manager.store_interaction("alguma coisa", "resposta")
        assert memory_manager.get_relevant_context("") == []

    def test_get_relevant_context_max_results(self, tmp_path):
        """Deve respeitar o parâmetro max_results."""
        mm = MemoryManager(storage_path=str(tmp_path / "mem.json"), max_interactions=100)
        for i in range(10):
            mm.store_interaction(f"python código exemplo {i}", f"resposta {i}")
        result = mm.get_relevant_context("python código", max_results=3)
        assert len(result) <= 3

    def test_get_relevant_context_no_match_returns_empty(self, memory_manager):
        """Deve retornar lista vazia quando não há matches."""
        memory_manager.store_interaction("falar sobre bananas", "bananas são frutas")
        result = memory_manager.get_relevant_context("python programação")
        assert result == []

    def test_results_ordered_by_score_descending(self, tmp_path):
        """Resultados devem ser ordenados por relevância (mais relevante primeiro)."""
        mm = MemoryManager(storage_path=str(tmp_path / "mem.json"), max_interactions=100)
        # Alta relevância: contém 3 keywords
        mm.store_interaction("python código dados ciência", "resposta alta relevância")
        # Baixa relevância: contém apenas 1 keyword
        mm.store_interaction("python básico", "resposta baixa relevância")
        result = mm.get_relevant_context("python código dados ciência")
        assert result[0]["user"] == "python código dados ciência"


class TestMemoryManagerExecute:
    def test_execute_returns_relevant_context(self, memory_manager):
        """execute() deve retornar contexto relevante para a query fornecida."""
        memory_manager.store_interaction("qual é o clima?", "Está quente.")
        result = memory_manager.execute({"query": "clima temperatura"})
        assert result["success"] is True
        assert isinstance(result["relevant_context"], list)

    def test_execute_with_empty_context_returns_failure(self, memory_manager):
        """execute() com contexto vazio deve retornar falha."""
        result = memory_manager.execute(None)
        assert result["success"] is False

    def test_execute_with_no_query_returns_empty_context(self, memory_manager):
        """execute() sem query deve retornar contexto vazio."""
        result = memory_manager.execute({})
        assert result["success"] is True
        assert result["relevant_context"] == []
