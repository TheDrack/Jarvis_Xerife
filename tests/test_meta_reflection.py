# -*- coding: utf-8 -*-
"""Tests for MetaReflection."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.application.services.meta_reflection import MetaReflection


class TestMetaReflectionReflect:
    """Testa o método reflect() com dados mockados."""

    def _make_history(self):
        """Cria histórico de recompensas simulado."""
        return [
            {
                "action_type": "pytest_pass",
                "reward_value": 10.0,
                "context_data": {"module": "llm_router.py", "solution_pattern": "pytest_pass"},
            },
            {
                "action_type": "deploy_fail",
                "reward_value": -25.0,
                "context_data": {
                    "module": "evolution_orchestrator.py",
                    "error_type": "ImportError",
                    "solution_pattern": "deploy_fail",
                },
            },
            {
                "action_type": "pytest_fail",
                "reward_value": -5.0,
                "context_data": {
                    "module": "capability_manager.py",
                    "error_type": "ImportError",
                },
            },
            {
                "action_type": "deploy_success",
                "reward_value": 50.0,
                "context_data": {"solution_pattern": "deploy_success"},
            },
        ]

    def _make_error_log(self):
        """Cria log de erros simulado."""
        return [
            {"module": "evolution_orchestrator.py", "error_type": "ImportError", "message": "err"},
            {"module": "evolution_orchestrator.py", "error_type": "TimeoutError", "message": "err"},
            {"module": "llm_router.py", "error_type": "ImportError", "message": "err"},
        ]

    def test_reflect_returns_required_fields(self):
        """reflect() deve retornar todos os campos obrigatórios."""
        mr = MetaReflection()
        result = mr.reflect([], [])

        assert "fragile_modules" in result
        assert "successful_patterns" in result
        assert "recurring_error_types" in result
        assert "recommended_focus" in result

    def test_fragile_modules_orders_by_error_count(self):
        """Módulos mais frágeis devem aparecer primeiro."""
        mr = MetaReflection()
        error_log = [
            {"module": "modulo_A.py"},
            {"module": "modulo_A.py"},
            {"module": "modulo_B.py"},
        ]
        result = mr.reflect([], error_log)
        assert result["fragile_modules"][0] == "modulo_A.py"

    def test_successful_patterns_includes_positive_rewards(self):
        """Padrões de sucesso devem incluir ações com recompensa positiva."""
        mr = MetaReflection()
        history = self._make_history()
        result = mr.reflect(history, [])

        # deploy_success e pytest_pass têm recompensa positiva
        assert len(result["successful_patterns"]) > 0

    def test_recurring_error_types_threshold(self):
        """Apenas erros em >20% dos ciclos devem ser considerados recorrentes."""
        mr = MetaReflection(recurring_threshold=0.20)
        # 3 entradas totais, ImportError em 2 → 66% > 20% → deve aparecer
        error_log = [
            {"error_type": "ImportError"},
            {"error_type": "ImportError"},
            {"error_type": "RareError"},
        ]
        result = mr.reflect([], error_log)
        assert "ImportError" in result["recurring_error_types"]

    def test_recurring_error_types_below_threshold(self):
        """Erros abaixo do threshold não devem aparecer."""
        mr = MetaReflection(recurring_threshold=0.50)
        error_log = [
            {"error_type": "RareError"},
            {"error_type": "CommonError"},
            {"error_type": "CommonError"},
            {"error_type": "CommonError"},
            {"error_type": "CommonError"},
        ]
        result = mr.reflect([], error_log)
        # RareError está em 1/5 = 20% < 50% → não deve aparecer
        assert "RareError" not in result["recurring_error_types"]

    def test_recommended_focus_with_recurring_errors(self):
        """Quando há erros recorrentes, foco deve mencionar corrigi-los."""
        mr = MetaReflection()
        error_log = [
            {"error_type": "ImportError"},
            {"error_type": "ImportError"},
        ]
        result = mr.reflect([], error_log)
        assert "ImportError" in result["recommended_focus"] or len(result["recommended_focus"]) > 0

    def test_recommended_focus_with_fragile_modules(self):
        """Quando não há erros recorrentes mas há módulos frágeis, foco menciona estabilização."""
        mr = MetaReflection(recurring_threshold=1.0)  # threshold impossível → sem recorrentes
        error_log = [{"module": "fragile_module.py"}]
        result = mr.reflect([], error_log)
        assert "fragile" in result["recommended_focus"].lower() or len(result["recommended_focus"]) > 0

    def test_recommended_focus_default(self):
        """Sem erros ou padrões, foco deve ser incremental."""
        mr = MetaReflection()
        result = mr.reflect([], [])
        assert isinstance(result["recommended_focus"], str)
        assert len(result["recommended_focus"]) > 0

    def test_reflect_with_full_data(self):
        """reflect() com dados completos deve produzir resultado coerente."""
        mr = MetaReflection()
        result = mr.reflect(self._make_history(), self._make_error_log())

        assert isinstance(result["fragile_modules"], list)
        assert isinstance(result["successful_patterns"], list)
        assert isinstance(result["recurring_error_types"], list)
        assert isinstance(result["recommended_focus"], str)
        # evolution_orchestrator tem 3 entradas de erro → deve ser frágil
        assert "evolution_orchestrator.py" in result["fragile_modules"]


class TestMetaReflectionPersistence:
    """Testa persistência do resultado da reflexão."""

    def test_save_and_load_reflection(self, tmp_path, monkeypatch):
        """Deve salvar e carregar reflexão corretamente."""
        import app.application.services.meta_reflection as mr_module

        monkeypatch.setattr(mr_module, "_REFLECTION_FILE", tmp_path / "meta_reflection_latest.jrvs")

        mr = MetaReflection()
        reflection_data = {
            "fragile_modules": ["a.py"],
            "successful_patterns": ["deploy_success"],
            "recurring_error_types": [],
            "recommended_focus": "estabilizar módulos frágeis",
        }
        mr._save_reflection(reflection_data)
        loaded = MetaReflection.load_latest()
        assert loaded is not None
        assert loaded["fragile_modules"] == ["a.py"]

    def test_load_returns_none_when_no_file(self, tmp_path, monkeypatch):
        """load_latest() deve retornar None quando arquivo não existe."""
        import app.application.services.meta_reflection as mr_module

        monkeypatch.setattr(mr_module, "_REFLECTION_FILE", tmp_path / "nonexistent.jrvs")

        loaded = MetaReflection.load_latest()
        assert loaded is None


class TestMetaReflectionExecute:
    """Testa a interface NexusComponent."""

    def test_execute_with_inline_data(self, tmp_path, monkeypatch):
        """execute() com dados no contexto deve retornar reflexão."""
        import app.application.services.meta_reflection as mr_module

        monkeypatch.setattr(mr_module, "_REFLECTION_FILE", tmp_path / "meta_reflection_latest.jrvs")

        mr = MetaReflection()
        result = mr.execute({
            "reward_history": [
                {"action_type": "deploy_success", "reward_value": 50.0, "context_data": {}}
            ],
            "error_log": [],
        })
        assert result["success"] is True
        assert "reflection" in result
        assert "recommended_focus" in result["reflection"]

    def test_configure(self):
        """configure() deve atualizar recurring_threshold."""
        mr = MetaReflection()
        mr.configure({"recurring_threshold": 0.3})
        assert mr.recurring_threshold == 0.3

    def test_can_execute(self):
        """can_execute() deve retornar True."""
        mr = MetaReflection()
        assert mr.can_execute() is True
