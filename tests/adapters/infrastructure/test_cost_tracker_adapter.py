# -*- coding: utf-8 -*-
"""Tests for CostTrackerAdapter — MELHORIA 7."""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.infrastructure.cost_tracker_adapter import CostTrackerAdapter, _load_price_table


@pytest.fixture
def tracker(tmp_path):
    db = str(tmp_path / "test_cost.db")
    return CostTrackerAdapter(db_path=db)


class TestCostTrackerInit:
    def test_defaults(self, tracker):
        assert tracker._engine is None
        assert tracker._price_table == {}

    def test_uses_database_url_if_provided(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'alt.db'}"
        t = CostTrackerAdapter(database_url=url)
        assert t._database_url == url


class TestCostTrackerLog:
    def test_log_creates_engine_and_records(self, tracker):
        """log() deve criar a tabela e registrar uma entrada."""
        tracker.log(
            model="llama-3.3-70b",
            task_type="code_generation",
            prompt_tokens=100,
            completion_tokens=50,
            success=True,
        )
        summary = tracker.get_cost_summary(period_days=1)
        assert summary["total"] >= 0.0
        assert "llama-3.3-70b" in summary["by_model"]
        assert "code_generation" in summary["by_task_type"]

    def test_log_multiple_models(self, tracker):
        tracker.log("model-a", "code_generation", 100, 50, True)
        tracker.log("model-b", "reasoning", 200, 100, True)
        summary = tracker.get_cost_summary(period_days=1)
        assert "model-a" in summary["by_model"]
        assert "model-b" in summary["by_model"]
        assert "code_generation" in summary["by_task_type"]
        assert "reasoning" in summary["by_task_type"]


class TestCostTrackerGetSummary:
    def test_summary_empty_returns_zeros(self, tracker):
        summary = tracker.get_cost_summary(period_days=7)
        assert summary["total"] == 0.0
        assert summary["by_model"] == {}
        assert summary["by_task_type"] == {}

    def test_summary_period_days_field_present(self, tracker):
        summary = tracker.get_cost_summary(period_days=30)
        assert summary["period_days"] == 30


class TestCostTrackerMedian:
    def test_get_median_cost_empty(self, tracker):
        result = tracker.get_median_cost("code_generation")
        assert result == 0.0

    def test_get_median_cost_with_data(self, tracker):
        tracker.log("model-x", "code_generation", 100, 50, True)
        tracker.log("model-x", "code_generation", 200, 100, True)
        tracker.log("model-x", "code_generation", 300, 150, True)
        median = tracker.get_median_cost("code_generation")
        assert median >= 0.0


class TestCostTrackerEstimate:
    def test_estimate_uses_default_prices(self, tracker):
        cost = tracker._estimate_cost("unknown-model", 1000, 500)
        # (1000 * 0.0001 + 500 * 0.0002) / 1000 = (0.1 + 0.1) / 1000 = 0.0002
        assert cost == pytest.approx(0.0002, rel=0.01)

    def test_estimate_zero_tokens(self, tracker):
        cost = tracker._estimate_cost("unknown-model", 0, 0)
        assert cost == 0.0
