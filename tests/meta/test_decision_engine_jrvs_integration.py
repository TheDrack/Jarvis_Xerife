# -*- coding: utf-8 -*-
"""Tests de integração DecisionEngine + JRVSCompiler (snapshots .jrvs)."""

import pytest

from app.core.meta.decision_engine import DecisionEngine, DecisionResult
from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore


@pytest.fixture()
def tmp_store(tmp_path):
    return PolicyStore(jrvs_dir=str(tmp_path))


@pytest.fixture()
def compiler(tmp_path, tmp_store):
    return JRVSCompiler(policy_store=tmp_store, jrvs_dir=str(tmp_path))


@pytest.fixture()
def engine(compiler, tmp_store):
    return DecisionEngine(compiler=compiler, policy_store=tmp_store)


class TestDecisionEngineJrvsIntegration:
    """Verifica que DecisionEngine usa snapshot .jrvs e reload_module funciona."""

    def test_decide_returns_decision_result(self, engine):
        result = engine.decide({"command": "teste"})
        assert isinstance(result, DecisionResult)

    def test_decide_uses_jrvs_snapshot(self, tmp_path, tmp_store, compiler):
        """Após compilar módulo llm, decide() deve usar snapshot .jrvs."""
        policies = {
            "groq": {"ema_success": 0.9, "uses": 5},
            "gemini": {"ema_success": 0.6, "uses": 3},
        }
        tmp_store.update_policies("llm", policies)
        compiler.compile_module("llm")

        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)
        result = engine.decide({"command": "test"})
        # Groq has higher ema_success → should be chosen
        assert result.chosen == "groq"
        assert result.score == pytest.approx(0.9, abs=1e-6)

    def test_decide_fallback_when_no_jrvs(self, tmp_path, tmp_store, compiler):
        """Sem .jrvs compilado, deve recorrer ao PolicyStore."""
        policies = {"fallback_llm": {"ema_success": 0.55}}
        tmp_store.update_policies("llm", policies)
        # Do NOT compile — force fallback
        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)
        result = engine.decide({"command": "test"})
        assert result.chosen == "fallback_llm"
        assert result.jrvs_version == "fallback"

    def test_decide_default_when_empty(self, engine):
        """Sem políticas e sem .jrvs, retorna 'default'."""
        result = engine.decide({"command": "test"})
        assert result.chosen == "default"

    def test_reload_module_picks_up_changes(self, tmp_path, tmp_store, compiler):
        """reload_module() deve atualizar o snapshot em memória."""
        tmp_store.update_policies("llm", {"old_llm": {"ema_success": 0.4}})
        compiler.compile_module("llm")
        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)

        # Update policies and recompile
        tmp_store.update_policies("llm", {"new_llm": {"ema_success": 0.95}})
        compiler.compile_module("llm")

        # Before reload, snapshot may still be stale
        engine.reload_module("llm")

        result = engine.decide({"command": "after reload"})
        assert result.chosen == "new_llm"

    def test_reload_module_returns_false_for_missing(self, engine):
        ok = engine.reload_module("nonexistent_xyz")
        assert ok is False

    def test_jrvs_version_in_result(self, tmp_path, tmp_store, compiler):
        """jrvs_version no resultado deve refletir a versão do compiler."""
        tmp_store.update_policies("llm", {"x": {"ema_success": 0.7}})
        compiler.compile_module("llm")
        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)
        result = engine.decide({})
        assert result.jrvs_version != "fallback"

    def test_execute_interface(self, tmp_path, tmp_store, compiler):
        """execute() deve retornar dict com success=True."""
        tmp_store.update_policies("llm", {"groq": {"ema_success": 0.8}})
        compiler.compile_module("llm")
        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)
        out = engine.execute({"command": "test"})
        assert out["success"] is True
        assert "chosen" in out

    def test_trigger_recompile(self, tmp_path, tmp_store, compiler):
        """trigger_recompile deve compilar e recarregar o snapshot."""
        tmp_store.update_policies("llm", {"alpha": {"ema_success": 0.7}})
        engine = DecisionEngine(compiler=compiler, policy_store=tmp_store)

        tmp_store.update_policies("llm", {"beta": {"ema_success": 0.95}})
        ok = engine.trigger_recompile("llm")
        assert ok is True
        result = engine.decide({})
        assert result.chosen == "beta"
