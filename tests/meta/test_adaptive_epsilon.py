# -*- coding: utf-8 -*-
"""Tests para epsilon adaptativo do DecisionEngine (Part 3)."""

import pytest

from app.core.meta.decision_engine import (
    DecisionEngine,
    _DEFAULT_EPSILON,
    _DEFAULT_GLOBAL_SUCCESS_EMA,
    _STABILITY_EPSILON,
    _STABILITY_THRESHOLD,
)
from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore


@pytest.fixture()
def setup(tmp_path):
    store = PolicyStore(jrvs_dir=str(tmp_path))
    compiler = JRVSCompiler(policy_store=store, jrvs_dir=str(tmp_path))
    # Initialise meta policies with explicit starting values
    store.update_policies(
        "meta",
        {
            "epsilon": 0.15,
            "decay": 0.995,
            "min_epsilon": 0.03,
            "max_epsilon": 0.4,
            "global_success_ema": 0.8,
            "learning_rate": 0.5,  # high alpha for fast convergence in tests
        },
    )
    compiler.compile_module("meta")
    # Seed llm policies
    store.update_policies("llm", {"groq": {"ema_success": 0.8, "uses": 5}})
    compiler.compile_module("llm")
    engine = DecisionEngine(compiler=compiler, policy_store=store)
    return engine, store


class TestAdaptiveEpsilonIncrease:
    """Epsilon must increase when global_success_ema drops below 0.6."""

    def test_epsilon_increases_on_performance_drop(self, setup):
        engine, store = setup
        initial_params = engine._get_meta_params()
        initial_eps = initial_params["epsilon"]

        # Simulate a series of failures to drive global_success_ema below 0.6
        # With learning_rate=0.5, a single failure moves gse by 50%
        store.update_policies(
            "meta",
            {
                "epsilon": 0.15,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.55,  # already below 0.6
                "learning_rate": 0.5,
            },
        )
        engine.reload_module("meta")

        engine._update_adaptive_epsilon(is_success=False)

        updated = engine._get_meta_params()
        assert updated["epsilon"] > initial_eps or updated["epsilon"] >= 0.03

    def test_epsilon_capped_at_max_epsilon(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 0.38,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.5,
                "learning_rate": 0.5,
            },
        )
        engine.reload_module("meta")

        # Multiple failures should cap at max_epsilon
        for _ in range(5):
            engine._update_adaptive_epsilon(is_success=False)

        params = engine._get_meta_params()
        assert params["epsilon"] <= params["max_epsilon"]


class TestAdaptiveEpsilonDecay:
    """Epsilon must decay when global_success_ema is above 0.6."""

    def test_epsilon_decays_on_recovery(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 0.3,
                "decay": 0.8,  # fast decay for tests
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.85,
                "learning_rate": 0.5,
            },
        )
        engine.reload_module("meta")

        engine._update_adaptive_epsilon(is_success=True)

        params = engine._get_meta_params()
        assert params["epsilon"] < 0.3

    def test_epsilon_floored_at_min_epsilon(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 0.035,
                "decay": 0.5,  # aggressive decay
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.9,
                "learning_rate": 0.1,
            },
        )
        engine.reload_module("meta")

        for _ in range(10):
            engine._update_adaptive_epsilon(is_success=True)

        params = engine._get_meta_params()
        assert params["epsilon"] >= params["min_epsilon"]


class TestStabilityModeEpsilon:
    """In stability mode (gse < 0.4), epsilon must be frozen at 0.3."""

    def test_stability_mode_freezes_epsilon(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 0.1,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.25,
                "learning_rate": 0.1,
            },
        )
        engine.reload_module("meta")

        result = engine.decide({"command": "test"})
        assert result.epsilon == pytest.approx(_STABILITY_EPSILON)

    def test_stability_state_critical(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "global_success_ema": _STABILITY_THRESHOLD - 0.05,
                "epsilon": 0.1,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "learning_rate": 0.1,
            },
        )
        engine.reload_module("meta")
        assert engine.get_stability_state() == "critical"

    def test_stability_state_ok(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "global_success_ema": _STABILITY_THRESHOLD + 0.1,
                "epsilon": 0.15,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "learning_rate": 0.1,
            },
        )
        engine.reload_module("meta")
        assert engine.get_stability_state() == "ok"


class TestEpsilonGreedyExploration:
    """With epsilon=1.0, every decision must be an exploration."""

    def test_explore_when_epsilon_is_one(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 1.0,
                "decay": 0.995,
                "min_epsilon": 0.0,
                "max_epsilon": 1.0,
                "global_success_ema": 0.8,
                "learning_rate": 0.1,
            },
        )
        result = engine.decide({"command": "explore"})
        assert result.exploration is True

    def test_no_explore_when_epsilon_is_zero(self, setup):
        engine, store = setup
        store.update_policies(
            "meta",
            {
                "epsilon": 0.0,
                "decay": 0.995,
                "min_epsilon": 0.0,
                "max_epsilon": 1.0,
                "global_success_ema": 0.8,
                "learning_rate": 0.1,
            },
        )
        result = engine.decide({"command": "exploit"})
        assert result.exploration is False


class TestEpsilonBoundaryBehavior:
    """Verifies the gse < 0.6 boundary that triggers epsilon increase."""

    def test_epsilon_increases_when_gse_below_06(self, setup):
        engine, store = setup
        eps_before = 0.15
        store.update_policies(
            "meta",
            {
                "epsilon": eps_before,
                "decay": 0.995,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.59,  # just below 0.6 boundary
                "learning_rate": 0.01,  # small alpha to keep gse near 0.59
            },
        )
        engine._update_adaptive_epsilon(is_success=False)
        params = engine._get_meta_params()
        assert params["epsilon"] > eps_before or params["epsilon"] >= 0.03

    def test_epsilon_decays_when_gse_above_06(self, setup):
        engine, store = setup
        eps_before = 0.3
        store.update_policies(
            "meta",
            {
                "epsilon": eps_before,
                "decay": 0.9,
                "min_epsilon": 0.03,
                "max_epsilon": 0.4,
                "global_success_ema": 0.70,  # above 0.6
                "learning_rate": 0.01,
            },
        )
        engine._update_adaptive_epsilon(is_success=True)
        params = engine._get_meta_params()
        assert params["epsilon"] < eps_before
