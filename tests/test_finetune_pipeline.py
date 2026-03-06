# -*- coding: utf-8 -*-
"""Tests for FineTuneDatasetCollector and FineTuneTriggerService (Etapa 9)."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.finetune_dataset_collector import FineTuneDatasetCollector
from app.application.services.finetune_trigger_service import FineTuneTriggerService


# ---- FineTuneDatasetCollector ------------------------------------------------


@pytest.fixture
def collector():
    return FineTuneDatasetCollector()


class TestFineTuneDatasetCollectorDefaults:
    def test_defaults(self, collector):
        assert collector.min_reward == 0.7

    def test_configure(self, collector):
        collector.configure({"min_reward": 0.5})
        assert collector.min_reward == 0.5


class TestFineTuneDatasetCollectorCollect:
    def _make_thought(self, problem, solution, success=True, reward=None):
        """Helper: cria um mock de ThoughtLog."""
        t = MagicMock()
        t.success = success
        t.problem_description = problem
        t.solution_attempt = solution
        t.reward_value = reward
        return t

    def test_collect_filters_by_success(self, collector):
        """Deve incluir apenas pensamentos bem-sucedidos."""
        thoughts = [
            self._make_thought("p1", "s1", success=True),
            self._make_thought("p2", "s2", success=False),
            self._make_thought("p3", "s3", success=True),
        ]

        mock_tls = MagicMock()
        mock_tls.get_recent_thoughts.return_value = thoughts

        with patch("app.application.services.finetune_dataset_collector.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_tls
            pairs = collector.collect(min_reward=0.0)

        assert len(pairs) == 2
        assert all(p["instruction"] != "" for p in pairs)
        assert all(p["output"] != "" for p in pairs)

    def test_collect_filters_by_reward(self, collector):
        """Deve filtrar por reward mínimo."""
        thoughts = [
            self._make_thought("p1", "s1", success=True, reward=0.9),
            self._make_thought("p2", "s2", success=True, reward=0.5),
            self._make_thought("p3", "s3", success=True, reward=0.8),
        ]

        mock_tls = MagicMock()
        mock_tls.get_recent_thoughts.return_value = thoughts

        with patch("app.application.services.finetune_dataset_collector.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_tls
            pairs = collector.collect(min_reward=0.7)

        # Apenas p1 (0.9) e p3 (0.8) passam
        assert len(pairs) == 2

    def test_collect_returns_empty_when_no_tls(self, collector):
        """Sem ThoughtLogService disponível, retorna lista vazia."""
        with patch("app.application.services.finetune_dataset_collector.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            pairs = collector.collect()
        assert pairs == []


class TestFineTuneDatasetCollectorExport:
    def test_export_creates_jsonl_file(self, collector, tmp_path):
        """export_dataset deve criar arquivo JSONL com uma entrada por linha."""
        pairs = [
            {"instruction": "Faça X", "output": "def x(): pass"},
            {"instruction": "Faça Y", "output": "def y(): pass"},
        ]
        output_path = str(tmp_path / "test_dataset.jsonl")
        result = collector.export_dataset(output_path, pairs=pairs)

        assert Path(result).exists()
        lines = Path(result).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        # Verifica formato JSON de cada linha
        for line in lines:
            entry = json.loads(line)
            assert "instruction" in entry
            assert "output" in entry

    def test_export_correct_format(self, collector, tmp_path):
        """Cada linha do JSONL deve ter campos 'instruction' e 'output'."""
        pairs = [{"instruction": "prompt aqui", "output": "def code(): pass"}]
        path = str(tmp_path / "dataset.jsonl")
        collector.export_dataset(path, pairs=pairs)

        entry = json.loads(Path(path).read_text(encoding="utf-8").strip())
        assert entry["instruction"] == "prompt aqui"
        assert entry["output"] == "def code(): pass"

    def test_export_creates_parent_dirs(self, collector, tmp_path):
        """export_dataset deve criar diretórios intermediários se necessário."""
        deep_path = str(tmp_path / "a" / "b" / "c" / "dataset.jsonl")
        collector.export_dataset(deep_path, pairs=[])
        assert Path(deep_path).exists()


# ---- FineTuneTriggerService --------------------------------------------------


@pytest.fixture
def trigger(tmp_path):
    svc = FineTuneTriggerService()
    # Aponta para diretório temporário para não poluir data/
    import app.application.services.finetune_trigger_service as ft_mod

    ft_mod._FINETUNE_DIR = tmp_path / "finetune"
    ft_mod._TRIGGER_META_FILE = ft_mod._FINETUNE_DIR / "trigger_latest.json"
    return svc


class TestFineTuneTriggerServiceDefaults:
    def test_defaults(self, trigger):
        assert trigger.pair_threshold == 50
        assert trigger.model_target == "qwen2.5-coder:14b"
        assert trigger.min_reward == 0.7

    def test_configure(self, trigger):
        trigger.configure({"pair_threshold": 10, "model_target": "llama3", "min_reward": 0.5})
        assert trigger.pair_threshold == 10
        assert trigger.model_target == "llama3"
        assert trigger.min_reward == 0.5


class TestFineTuneTriggerServiceThreshold:
    def test_no_trigger_below_threshold(self, trigger):
        """Não deve disparar quando número de novos pares está abaixo do threshold."""
        trigger.configure({"pair_threshold": 50})

        mock_collector = MagicMock()
        mock_collector.collect.return_value = [{"instruction": "p", "output": "c"}] * 10

        with patch("app.application.services.finetune_trigger_service.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_collector
            result = trigger.execute({})

        assert result["success"] is True
        assert result["triggered"] is False
        assert result["pair_count"] == 10

    def test_triggers_when_above_threshold(self, trigger, tmp_path):
        """Deve disparar quando há pares suficientes acima do threshold."""
        trigger.configure({"pair_threshold": 5})

        mock_collector = MagicMock()
        mock_collector.collect.return_value = [
            {"instruction": f"prompt_{i}", "output": f"code_{i}"} for i in range(10)
        ]
        exported_path = str(tmp_path / "finetune" / "dataset.jsonl")
        mock_collector.export_dataset.return_value = exported_path

        with patch("app.application.services.finetune_trigger_service.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_collector
            result = trigger.execute({})

        assert result["success"] is True
        assert result["triggered"] is True
        assert result["pair_count"] == 10
        mock_collector.export_dataset.assert_called_once()

    def test_trigger_writes_metadata(self, trigger, tmp_path):
        """Ao disparar, deve criar arquivo de metadados trigger_latest.json."""
        import app.application.services.finetune_trigger_service as ft_mod

        ft_mod._FINETUNE_DIR = tmp_path / "finetune"
        ft_mod._TRIGGER_META_FILE = ft_mod._FINETUNE_DIR / "trigger_latest.json"

        trigger.configure({"pair_threshold": 2, "model_target": "test-model"})

        mock_collector = MagicMock()
        mock_collector.collect.return_value = [
            {"instruction": "p", "output": "c"} for _ in range(5)
        ]
        mock_collector.export_dataset.return_value = str(tmp_path / "finetune" / "dataset.jsonl")

        with patch("app.application.services.finetune_trigger_service.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_collector
            trigger.execute({})

        meta_file = ft_mod._TRIGGER_META_FILE
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert meta["status"] == "pending"
        assert meta["model_target"] == "test-model"
        assert meta["pair_count"] == 5
        assert "triggered_at" in meta
