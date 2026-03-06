# -*- coding: utf-8 -*-
"""Tests for WorkingMemory and SemanticMemory."""

import pytest

from app.domain.memory.working_memory import WorkingMemory
from app.domain.memory.semantic_memory import SemanticMemory


class TestWorkingMemory:
    """Testa a memória de trabalho volátil."""

    def test_push_and_size(self):
        """push() deve incrementar o tamanho."""
        wm = WorkingMemory(maxlen=10)
        assert wm.size == 0
        wm.push({"role": "user", "content": "Olá"})
        assert wm.size == 1

    def test_push_requires_dict(self):
        """push() deve rejeitar entradas que não são dicionários."""
        wm = WorkingMemory()
        with pytest.raises(TypeError):
            wm.push("não é dict")  # type: ignore[arg-type]

    def test_overflow_discards_oldest(self):
        """Quando maxlen é atingido, a entrada mais antiga é descartada."""
        wm = WorkingMemory(maxlen=3)
        for i in range(5):
            wm.push({"idx": i})
        assert wm.size == 3
        recent = wm.get_recent(3)
        indices = [e["idx"] for e in recent]
        assert indices == [2, 3, 4]

    def test_get_recent_returns_correct_count(self):
        """get_recent(n) deve retornar no máximo n entradas."""
        wm = WorkingMemory(maxlen=10)
        for i in range(8):
            wm.push({"idx": i})
        assert len(wm.get_recent(5)) == 5
        assert len(wm.get_recent(20)) == 8  # menos do que solicitado

    def test_get_recent_zero_returns_empty(self):
        """get_recent(0) deve retornar lista vazia."""
        wm = WorkingMemory()
        wm.push({"x": 1})
        assert wm.get_recent(0) == []

    def test_clear(self):
        """clear() deve remover todas as entradas."""
        wm = WorkingMemory()
        wm.push({"a": 1})
        wm.push({"b": 2})
        wm.clear()
        assert wm.size == 0
        assert wm.get_recent(10) == []

    def test_entries_have_timestamp(self):
        """Entradas devem ter campo _ts adicionado automaticamente."""
        wm = WorkingMemory()
        wm.push({"content": "teste"})
        entry = wm.get_recent(1)[0]
        assert "_ts" in entry

    def test_maxlen_property(self):
        """maxlen deve refletir o valor configurado."""
        wm = WorkingMemory(maxlen=25)
        assert wm.maxlen == 25

    def test_len(self):
        """len() deve retornar o número de entradas."""
        wm = WorkingMemory(maxlen=10)
        wm.push({"x": 1})
        wm.push({"x": 2})
        assert len(wm) == 2


class TestSemanticMemory:
    """Testa a memória semântica baseada em grafo."""

    def test_add_fact_returns_id(self):
        """add_fact() deve retornar um ID único."""
        sm = SemanticMemory()
        fact_id = sm.add_fact("solution", "conteúdo do fato", confidence=0.9)
        assert isinstance(fact_id, str)
        assert len(fact_id) > 0

    def test_add_fact_increments_total(self):
        """Após adicionar fatos, total_facts deve aumentar."""
        sm = SemanticMemory()
        sm.add_fact("solution", "fato 1", 0.8)
        sm.add_fact("failure_pattern", "fato 2", 0.6)
        assert sm.total_facts == 2

    def test_query_by_fact_type(self):
        """query_facts() deve filtrar por fact_type."""
        sm = SemanticMemory()
        sm.add_fact("solution", "solução A", 0.9)
        sm.add_fact("solution", "solução B", 0.7)
        sm.add_fact("failure_pattern", "erro X", 0.5)

        solutions = sm.query_facts(fact_type="solution")
        assert len(solutions) == 2
        assert all(f["fact_type"] == "solution" for f in solutions)

    def test_query_by_min_confidence(self):
        """query_facts() deve filtrar por confiança mínima."""
        sm = SemanticMemory()
        sm.add_fact("solution", "alta", 0.9)
        sm.add_fact("solution", "baixa", 0.3)

        results = sm.query_facts(min_confidence=0.5)
        assert len(results) == 1
        assert results[0]["content"] == "alta"

    def test_query_sorted_by_confidence_desc(self):
        """query_facts() deve retornar resultados ordenados por confiança descendente."""
        sm = SemanticMemory()
        sm.add_fact("solution", "média", 0.5)
        sm.add_fact("solution", "alta", 0.9)
        sm.add_fact("solution", "baixa", 0.1)

        results = sm.query_facts(fact_type="solution")
        confidences = [r["confidence"] for r in results]
        assert confidences == sorted(confidences, reverse=True)

    def test_query_empty_type_returns_all(self):
        """query_facts() sem tipo deve retornar todos os fatos."""
        sm = SemanticMemory()
        sm.add_fact("solution", "fato 1", 0.8)
        sm.add_fact("failure_pattern", "fato 2", 0.6)

        results = sm.query_facts()
        assert len(results) == 2

    def test_confidence_clamped(self):
        """Confiança deve ser limitada entre 0 e 1."""
        sm = SemanticMemory()
        sm.add_fact("solution", "acima de 1", confidence=1.5)
        sm.add_fact("failure_pattern", "abaixo de 0", confidence=-0.5)

        results = sm.query_facts()
        for f in results:
            assert 0.0 <= f["confidence"] <= 1.0

    def test_consolidate_from_episodic_adds_facts(self):
        """consolidate_from_episodic() deve adicionar fatos da memória episódica."""
        sm = SemanticMemory()
        entries = [
            {"content": "solução para ImportError no módulo X", "success": True, "confidence": 0.8},
            {"content": "padrão de falha: timeout em chamada HTTP", "success": False},
            {"content": "curto"},  # abaixo do min_content_length (10 chars)
        ]
        count = sm.consolidate_from_episodic(entries)
        assert count == 2  # "curto" não deve ser indexado
        assert sm.total_facts == 2

    def test_consolidate_classifies_solutions_and_failures(self):
        """consolidate_from_episodic() deve criar 'solution' ou 'failure_pattern'."""
        sm = SemanticMemory()
        entries = [
            {"content": "solução que funcionou para corrigir erro", "success": True},
            {"content": "padrão de falha recorrente identificado", "success": False},
        ]
        sm.consolidate_from_episodic(entries)

        solutions = sm.query_facts(fact_type="solution")
        failures = sm.query_facts(fact_type="failure_pattern")
        assert len(solutions) == 1
        assert len(failures) == 1

    def test_consolidate_ignores_non_dict_entries(self):
        """consolidate_from_episodic() deve ignorar entradas não-dict."""
        sm = SemanticMemory()
        entries = ["não é dict", 42, None, {"content": "entrada válida com conteúdo suficiente"}]
        count = sm.consolidate_from_episodic(entries)
        assert count == 1

    def test_execute_add_fact_action(self):
        """execute() com action=add_fact deve adicionar um fato."""
        sm = SemanticMemory()
        result = sm.execute({
            "action": "add_fact",
            "fact_type": "solution",
            "content": "fato via execute",
            "confidence": 0.7,
        })
        assert result["success"] is True
        assert "fact_id" in result
        assert sm.total_facts == 1

    def test_execute_query_facts_action(self):
        """execute() com action=query_facts deve retornar fatos."""
        sm = SemanticMemory()
        sm.add_fact("solution", "fato A", 0.9)
        result = sm.execute({"action": "query_facts", "fact_type": "solution"})
        assert result["success"] is True
        assert len(result["facts"]) == 1

    def test_execute_stats_action(self):
        """execute() com action=stats deve retornar estatísticas."""
        sm = SemanticMemory()
        sm.add_fact("solution", "fato A", 0.9)
        result = sm.execute({"action": "stats"})
        assert result["success"] is True
        assert result["total_facts"] == 1
        assert "solution" in result["fact_types"]
