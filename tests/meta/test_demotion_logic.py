# -*- coding: utf-8 -*-
"""Tests para lógica de demoção e quarentena automática (Part 4)."""

import pytest

from app.core.meta.decision_engine import (
    DecisionEngine,
    _DEMOTE_FAILURE_RATE,
    _DEMOTE_MIN_TOTAL,
    _QUARANTINE_FAILURE_RATE,
    _QUARANTINE_MIN_TOTAL,
    _RECOVERY_CONSECUTIVE,
)
from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore


def _make_engine(tmp_path, policies=None):
    store = PolicyStore(jrvs_dir=str(tmp_path))
    compiler = JRVSCompiler(policy_store=store, jrvs_dir=str(tmp_path))
    store.update_policies("llm", policies or {"model_a": {"ema_success": 0.8}})
    store.update_policies(
        "meta",
        {
            "epsilon": 0.0,  # no exploration for deterministic tests
            "decay": 0.995,
            "min_epsilon": 0.0,
            "max_epsilon": 0.4,
            "global_success_ema": 0.8,
            "learning_rate": 0.1,
        },
    )
    compiler.compile_module("llm")
    compiler.compile_module("meta")
    return DecisionEngine(compiler=compiler, policy_store=store), store


class TestDemotionLogic:
    """Confidence must be halved when failure_rate > 0.6 and total >= 5."""

    def test_demotion_reduces_confidence(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"model_a": {"ema_success": 0.9, "confidence": 1.0}},
        )
        # Force counters to reach demotion threshold directly
        policies = store.get_policies_by_module("llm")
        policies["model_a"]["success_count"] = 1
        policies["model_a"]["failure_count"] = 4  # total=5, failure_rate=0.8
        store.update_policies("llm", policies)
        engine.reload_module("llm")

        engine.register_feedback("model_a", "failure")

        updated = store.get_policies_by_module("llm")["model_a"]
        assert updated["confidence"] < 1.0

    def test_no_demotion_below_min_total(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"model_b": {"ema_success": 0.1, "confidence": 1.0}},
        )
        # Only 3 total executions — below threshold
        policies = store.get_policies_by_module("llm")
        policies["model_b"]["success_count"] = 0
        policies["model_b"]["failure_count"] = 3
        store.update_policies("llm", policies)
        engine.reload_module("llm")

        engine.register_feedback("model_b", "failure")

        updated = store.get_policies_by_module("llm")["model_b"]
        assert updated.get("confidence", 1.0) == pytest.approx(1.0, abs=1e-6)


class TestQuarantineLogic:
    """Policy must be quarantined when failure_rate > 0.75 and total >= 10."""

    def test_quarantine_triggered(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"bad_model": {"ema_success": 0.1, "confidence": 1.0}},
        )
        policies = store.get_policies_by_module("llm")
        policies["bad_model"]["success_count"] = 2
        policies["bad_model"]["failure_count"] = 8  # total=10, failure_rate=0.8
        store.update_policies("llm", policies)
        engine.reload_module("llm")

        engine.register_feedback("bad_model", "failure")

        updated = store.get_policies_by_module("llm")["bad_model"]
        assert updated.get("quarantined") is True
        assert updated["confidence"] == pytest.approx(0.1)

    def test_quarantined_skipped_in_scoring(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {
                "bad_model": {"ema_success": 0.9, "quarantined": True, "confidence": 0.1},
                "good_model": {"ema_success": 0.7, "confidence": 1.0},
            },
        )
        result = engine.decide({"command": "test"})
        assert result.chosen == "good_model"

    def test_quarantine_recovery_after_consecutive_successes(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"recovering_model": {"ema_success": 0.5, "quarantined": True, "confidence": 0.1}},
        )
        # Register enough consecutive successes
        for _ in range(_RECOVERY_CONSECUTIVE):
            engine.register_feedback("recovering_model", "success")

        updated = store.get_policies_by_module("llm")["recovering_model"]
        assert "quarantined" not in updated or updated.get("quarantined") is not True
        assert updated.get("confidence", 0) > 0.1

    def test_quarantine_not_triggered_below_total(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"borderline": {"ema_success": 0.2, "confidence": 1.0}},
        )
        policies = store.get_policies_by_module("llm")
        policies["borderline"]["success_count"] = 1
        policies["borderline"]["failure_count"] = 7  # total=8 < 10
        store.update_policies("llm", policies)
        engine.reload_module("llm")

        engine.register_feedback("borderline", "failure")

        updated = store.get_policies_by_module("llm")["borderline"]
        assert not updated.get("quarantined")


class TestStabilityModeBlocksDemotion:
    """In critical stability mode, demotion and quarantine must not fire."""

    def test_no_demotion_in_stability_mode(self, tmp_path):
        engine, store = _make_engine(
            tmp_path,
            {"fragile_model": {"ema_success": 0.3, "confidence": 1.0}},
        )
        # Enter stability mode
        store.update_policies(
            "meta",
            {
                "global_success_ema": 0.2,
                "epsilon": 0.3,
                "decay": 0.995,
                "min_epsilon": 0.0,
                "max_epsilon": 0.4,
                "learning_rate": 0.1,
            },
        )
        engine.reload_module("meta")

        policies = store.get_policies_by_module("llm")
        policies["fragile_model"]["success_count"] = 2
        policies["fragile_model"]["failure_count"] = 8  # would normally quarantine
        store.update_policies("llm", policies)
        engine.reload_module("llm")

        engine.register_feedback("fragile_model", "failure")

        updated = store.get_policies_by_module("llm")["fragile_model"]
        assert not updated.get("quarantined")
        assert updated.get("confidence", 1.0) == pytest.approx(1.0, abs=1e-6)
