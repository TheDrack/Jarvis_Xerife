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


def test_memory_manager_redacts_pii_before_persisting_user_and_assistant_text(tmp_path):
    storage = tmp_path / "pii_memory.json"
    manager = MemoryManager(storage_path=str(storage))

    manager.store_interaction(
        "Contact alice.smith@example.com, CPF 123.456.789-09",
        "Use phone 48 99999-9999 for the callback.",
    )

    persisted = storage.read_text(encoding="utf-8")
    records = json.loads(persisted)
    assert "[EMAIL_REDACTED]" in records[0]["user"]
    assert "[CPF_REDACTED]" in records[0]["user"]
    assert "[PHONE_REDACTED]" in records[0]["jarvis"]
    assert "alice.smith@example.com" not in persisted
    assert "123.456.789-09" not in persisted
    assert "48 99999-9999" not in persisted


def test_memory_manager_sanitizes_legacy_file_before_returning_context(tmp_path):
    storage = tmp_path / "legacy_memory.json"
    storage.write_text(
        json.dumps([{
            "timestamp": "2026-11-01T10:00:00",
            "user": "Email alice@example.com",
            "jarvis": "CPF 123.456.789-09",
        }]),
        encoding="utf-8",
    )
    manager = MemoryManager(storage_path=str(storage))

    context = manager.get_relevant_context("email cpf")

    assert len(context) == 1
    assert "[EMAIL_REDACTED]" in context[0]["user"]
    assert "[CPF_REDACTED]" in context[0]["jarvis"]
    persisted = storage.read_text(encoding="utf-8")
    assert "alice@example.com" not in persisted
    assert "123.456.789-09" not in persisted


def test_memory_manager_fails_closed_when_injected_redactor_raises(tmp_path):
    class BrokenRedactor:
        def sanitize(self, _text):
            raise RuntimeError("redaction unavailable")

    storage = tmp_path / "blocked_memory.json"
    manager = MemoryManager(
        storage_path=str(storage),
        pii_redactor=BrokenRedactor(),
    )

    with pytest.raises(RuntimeError, match="redaction unavailable"):
        manager.store_interaction("private email alice@example.com", "response")

    assert not storage.exists()



def test_file_memory_is_partitioned_by_authenticated_user(tmp_path):
    manager = MemoryManager(storage_path=str(tmp_path / "memory.json"))

    manager.store_interaction(
        "private project aurora alice",
        "alice response",
        user_id="alice",
    )
    manager.store_interaction(
        "private project borealis bob",
        "bob response",
        user_id="bob",
    )

    alice = manager.get_relevant_context("private project aurora", user_id="alice")
    bob = manager.get_relevant_context("private project borealis", user_id="bob")

    assert len(alice) == 1
    assert alice[0]["user"] == "private project aurora alice"
    assert len(bob) == 1
    assert bob[0]["user"] == "private project borealis bob"
    assert manager.get_relevant_context("private project", user_id=None) == []


def test_scoped_memory_never_falls_back_to_legacy_unscoped_file(tmp_path):
    manager = MemoryManager(storage_path=str(tmp_path / "memory.json"))
    manager.store_interaction("legacy private project", "legacy response")

    assert manager.get_relevant_context("legacy private project", user_id="alice") == []


def test_user_scoped_memory_paths_do_not_expose_user_identifiers(tmp_path):
    manager = MemoryManager(storage_path=str(tmp_path / "memory.json"))
    manager.store_interaction("private memory marker", "response", user_id="alice@example.com")

    scoped_files = list((tmp_path / "memory.json.users").glob("*.json"))
    assert len(scoped_files) == 1
    assert "alice@example.com" not in scoped_files[0].name
    assert not (tmp_path / "memory.json").exists()


def test_memory_readback_survives_manager_recreation(tmp_path):
    """A new manager instance must recover the previously stored interaction."""
    storage_path = str(tmp_path / "restart_memory.json")
    first_manager = MemoryManager(storage_path=storage_path)
    first_manager.store_interaction(
        "configure the Jarvis network connector",
        "Use the authenticated connector and verify its health.",
    )

    restarted_manager = MemoryManager(storage_path=storage_path)
    recovered = restarted_manager.get_relevant_context(
        "Jarvis network connector"
    )

    assert len(recovered) == 1
    assert recovered[0]["user"] == "configure the Jarvis network connector"
    assert recovered[0]["jarvis"] == (
        "Use the authenticated connector and verify its health."
    )
