# -*- coding: utf-8 -*-
"""Tests for ProceduralMemoryAdapter — MELHORIA 3."""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.infrastructure.procedural_memory_adapter import (
    ProceduralMemoryAdapter,
    _vectorize,
    _cosine,
)


@pytest.fixture
def adapter():
    return ProceduralMemoryAdapter(similarity_threshold=0.80)


class TestProceduralMemoryInit:
    def test_defaults(self, adapter):
        assert adapter._threshold == 0.80
        assert adapter._solutions == []

    def test_configure(self, adapter):
        adapter.configure({"similarity_threshold": 0.90})
        assert adapter._threshold == 0.90


class TestProceduralMemoryIndexNewSolution:
    def test_index_successful_thought(self, adapter):
        """Deve indexar ThoughtLog com success=True."""
        thought = {
            "id": 1,
            "problem_description": "NullPointerError no método execute",
            "solution_attempt": "Add null check before calling execute",
            "success": True,
        }
        with patch.object(adapter, "_fetch_thought_log", return_value=thought):
            result = adapter.index_new_solution(1)
        assert result is True
        assert len(adapter._solutions) == 1
        assert adapter._solutions[0]["id"] == 1

    def test_skip_failed_thought(self, adapter):
        """Não deve indexar ThoughtLog com success=False."""
        thought = {
            "id": 2,
            "problem_description": "algum erro",
            "solution_attempt": "",
            "success": False,
        }
        with patch.object(adapter, "_fetch_thought_log", return_value=thought):
            result = adapter.index_new_solution(2)
        assert result is False
        assert len(adapter._solutions) == 0

    def test_returns_false_when_not_found(self, adapter):
        """Retorna False quando ThoughtLog não existe."""
        with patch.object(adapter, "_fetch_thought_log", return_value=None):
            result = adapter.index_new_solution(999)
        assert result is False


class TestProceduralMemorySearchSolution:
    def _add_solution(self, adapter, problem: str, solution: str, id_: int = 1):
        from app.adapters.infrastructure.procedural_memory_adapter import _vectorize
        vec = _vectorize(problem)
        adapter._solutions.append(
            {"id": id_, "problem": problem, "solution_attempt": solution, "vector": vec}
        )

    def test_search_high_similarity_returns_result(self, adapter):
        """Busca com problema muito similar deve retornar resultado."""
        problem = "Erro de NullPointer no execute do componente XYZ"
        self._add_solution(adapter, problem, "Add null check", id_=1)
        # Busca com texto quase idêntico
        result = adapter.search_solution("Erro de NullPointer no execute do componente XYZ")
        assert result is not None
        assert result["solution_attempt"] == "Add null check"
        assert result["score"] >= adapter._threshold

    def test_search_low_similarity_returns_none(self, adapter):
        """Busca com problema completamente diferente deve retornar None."""
        self._add_solution(adapter, "banco de dados corrompido", "restaurar backup", id_=1)
        result = adapter.search_solution("python syntax error missing colon")
        assert result is None

    def test_search_empty_solutions_returns_none(self, adapter):
        result = adapter.search_solution("qualquer coisa")
        assert result is None

    def test_search_empty_problem_returns_none(self, adapter):
        self._add_solution(adapter, "algum problema", "alguma solução", id_=1)
        result = adapter.search_solution("")
        assert result is None


class TestProceduralMemoryExecute:
    def test_execute_status_returns_count(self, adapter):
        result = adapter.execute({})
        assert result["success"] is True
        assert result["indexed_count"] == 0

    def test_execute_search_action(self, adapter):
        with patch.object(adapter, "search_solution", return_value=None) as mock_search:
            result = adapter.execute({"action": "search", "problem": "test problem"})
        assert result["success"] is True
        mock_search.assert_called_once_with("test problem")

    def test_execute_index_action_missing_id(self, adapter):
        result = adapter.execute({"action": "index"})
        assert result["success"] is False
        assert "thought_log_id" in result["error"]
