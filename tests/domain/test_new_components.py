# -*- coding: utf-8 -*-
"""Tests for SystemStateTracker, RewardSignalProvider, SafetyGuardian, and ModelOrchestrator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SystemStateTracker
# ---------------------------------------------------------------------------

class TestSystemStateTracker:
    """Tests for SystemStateTracker domain service."""

    def _make_tracker(self, tmp_path):
        from app.domain.services.system_state_tracker import SystemStateTracker, _SNAPSHOTS_DIR
        with patch("app.domain.services.system_state_tracker._SNAPSHOTS_DIR", tmp_path / "snapshots"):
            (tmp_path / "snapshots").mkdir(parents=True, exist_ok=True)
            tracker = SystemStateTracker.__new__(SystemStateTracker)
            tracker._history = []
            return tracker

    def test_capture_snapshot_returns_dict(self, tmp_path):
        """capture_snapshot deve retornar dicionário com campos obrigatórios."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        with patch("app.domain.services.system_state_tracker._SNAPSHOTS_DIR", tmp_path / "snaps"):
            (tmp_path / "snaps").mkdir(parents=True, exist_ok=True)
            snapshot = tracker.capture_snapshot(decision_id="test-001")

        assert "timestamp" in snapshot
        assert "cpu_percent" in snapshot
        assert "ram_percent" in snapshot
        assert "integrity_hash" in snapshot
        assert snapshot["decision_id"] == "test-001"

    def test_capture_snapshot_adds_to_history(self, tmp_path):
        """capture_snapshot deve acumular histórico em memória."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        with patch("app.domain.services.system_state_tracker._SNAPSHOTS_DIR", tmp_path / "snaps"):
            (tmp_path / "snaps").mkdir(parents=True, exist_ok=True)
            tracker.capture_snapshot()
            tracker.capture_snapshot()

        assert len(tracker._history) == 2

    def test_get_health_metrics_empty(self):
        """get_health_metrics com histórico vazio deve retornar status 'unknown'."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        metrics = tracker.get_health_metrics()
        assert metrics["status"] == "unknown"
        assert metrics["metabolic_rate"] == 1.0

    def test_get_health_metrics_with_history(self):
        """get_health_metrics deve calcular metabolic_rate baseado em cpu/ram."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = [
            {"cpu_percent": 20.0, "ram_percent": 30.0},
            {"cpu_percent": 40.0, "ram_percent": 50.0},
        ]

        metrics = tracker.get_health_metrics()
        assert "metabolic_rate" in metrics
        assert metrics["metabolic_rate"] > 0
        assert "status" in metrics

    def test_integrity_hash_computed(self, tmp_path):
        """integrity_hash deve ser string hexadecimal de 16 chars."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        with patch("app.domain.services.system_state_tracker._SNAPSHOTS_DIR", tmp_path / "snaps"):
            (tmp_path / "snaps").mkdir(parents=True, exist_ok=True)
            snapshot = tracker.capture_snapshot()

        assert len(snapshot["integrity_hash"]) == 32

    def test_execute_snapshot_action(self, tmp_path):
        """execute() com action='snapshot' deve retornar snapshot."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        with patch("app.domain.services.system_state_tracker._SNAPSHOTS_DIR", tmp_path / "snaps"):
            (tmp_path / "snaps").mkdir(parents=True, exist_ok=True)
            result = tracker.execute({"action": "snapshot", "decision_id": "x1"})

        assert result["success"] is True
        assert "snapshot" in result

    def test_execute_health_action(self):
        """execute() com action='health' deve retornar health metrics."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = []

        result = tracker.execute({"action": "health"})
        assert result["success"] is True
        assert "health" in result

    def test_execute_history_action(self, tmp_path):
        """execute() com action='history' deve retornar lista de snapshots."""
        from app.domain.services.system_state_tracker import SystemStateTracker

        tracker = SystemStateTracker.__new__(SystemStateTracker)
        tracker._history = [{"cpu_percent": 10.0, "ram_percent": 20.0}]

        result = tracker.execute({"action": "history", "limit": 5})
        assert result["success"] is True
        assert isinstance(result["snapshots"], list)


# ---------------------------------------------------------------------------
# RewardSignalProvider
# ---------------------------------------------------------------------------

class TestRewardSignalProvider:
    """Tests for RewardSignalProvider domain service."""

    def _make_provider(self, tmp_path):
        from app.domain.services.reward_signal_provider import (
            RewardSignalProvider,
            _REPLAY_BUFFER_FILE,
            _ThoughtLogAudit,
        )
        with patch("app.domain.services.reward_signal_provider._REPLAY_BUFFER_FILE", tmp_path / "buffer.jsonl"):
            provider = RewardSignalProvider.__new__(RewardSignalProvider)
            from collections import deque
            provider._replay_buffer = deque(maxlen=1000)
            provider.thought_log = _ThoughtLogAudit(tmp_path / "thought_log.jsonl")
            return provider

    # -- Legado (_calculate_legacy_reward) --

    def test_legacy_reward_pytest_pass(self, tmp_path):
        """_calculate_legacy_reward: pytest_pass deve retornar reward positivo."""
        provider = self._make_provider(tmp_path)
        reward = provider._calculate_legacy_reward("pytest_pass")
        assert reward == 10.0

    def test_legacy_reward_deploy_success(self, tmp_path):
        """_calculate_legacy_reward: deploy_success deve retornar reward maior."""
        provider = self._make_provider(tmp_path)
        reward = provider._calculate_legacy_reward("deploy_success")
        assert reward == 50.0

    def test_legacy_reward_unknown_action(self, tmp_path):
        """_calculate_legacy_reward: ação desconhecida deve retornar 0.0."""
        provider = self._make_provider(tmp_path)
        reward = provider._calculate_legacy_reward("unknown_action")
        assert reward == 0.0

    def test_legacy_reward_with_test_growth(self, tmp_path):
        """_calculate_legacy_reward: crescimento no número de testes deve ampliar reward."""
        provider = self._make_provider(tmp_path)
        reward_base = provider._calculate_legacy_reward("pytest_pass")
        reward_with_growth = provider._calculate_legacy_reward("pytest_pass", tests_before=10, tests_after=15)
        assert reward_with_growth > reward_base

    def test_legacy_reward_with_test_regression(self, tmp_path):
        """_calculate_legacy_reward: redução no número de testes deve reduzir reward."""
        provider = self._make_provider(tmp_path)
        reward_base = provider._calculate_legacy_reward("pytest_pass")
        reward_regression = provider._calculate_legacy_reward("pytest_pass", tests_before=15, tests_after=10)
        assert reward_regression < reward_base

    # -- Novo calculate_reward (métricas reais) --

    def test_calculate_reward_all_improved(self, tmp_path):
        """calculate_reward: tudo melhorou → reward máximo (1.0)."""
        provider = self._make_provider(tmp_path)
        before = {"tests_passing_rate": 0.8, "avg_latency_ms": 500, "error_rate_24h": 0.05}
        after = {"tests_passing_rate": 0.9, "avg_latency_ms": 400, "error_rate_24h": 0.02}
        reward = provider.calculate_reward(before, after, human_approval=True)
        assert 0.0 <= reward <= 1.0
        assert reward > 0.9  # todos os componentes no máximo

    def test_calculate_reward_latency_degraded(self, tmp_path):
        """calculate_reward: latência piorou → penaliza score de latência."""
        provider = self._make_provider(tmp_path)
        before = {"tests_passing_rate": 1.0, "avg_latency_ms": 200, "error_rate_24h": 0.0}
        after = {"tests_passing_rate": 1.0, "avg_latency_ms": 700, "error_rate_24h": 0.0}
        reward = provider.calculate_reward(before, after, human_approval=True)
        assert reward < 1.0  # latência degradou

    def test_calculate_reward_no_human_approval(self, tmp_path):
        """calculate_reward: sem aprovação humana → -0.1 no score."""
        provider = self._make_provider(tmp_path)
        before = {"tests_passing_rate": 1.0, "avg_latency_ms": 200, "error_rate_24h": 0.0}
        after = {"tests_passing_rate": 1.0, "avg_latency_ms": 200, "error_rate_24h": 0.0}
        reward_approved = provider.calculate_reward(before, after, human_approval=True)
        reward_rejected = provider.calculate_reward(before, after, human_approval=False)
        assert reward_approved - reward_rejected == pytest.approx(0.1, abs=1e-6)

    def test_calculate_reward_default_states(self, tmp_path):
        """calculate_reward: estados vazios → reward padrão (latência igual, tests igual)."""
        provider = self._make_provider(tmp_path)
        reward = provider.calculate_reward({}, {}, human_approval=True)
        # latency_score = 0.3, error_score = 0.2, test_score = 0.4, human_score = 0.1 → 1.0
        assert reward == pytest.approx(1.0, abs=1e-4)

    def test_calculate_reward_logs_breakdown(self, tmp_path):
        """calculate_reward: breakdown deve ser registrado no thought_log."""
        import json
        provider = self._make_provider(tmp_path)
        log_path = tmp_path / "thought_log.jsonl"
        provider.thought_log = __import__(
            "app.domain.services.reward_signal_provider", fromlist=["_ThoughtLogAudit"]
        )._ThoughtLogAudit(log_path)
        provider.calculate_reward({"tests_passing_rate": 1.0}, {"tests_passing_rate": 1.0})
        assert log_path.exists()
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["event"] == "reward_calculated"
        assert "breakdown" in entry
        assert "test_score" in entry["breakdown"]

    # -- calculate_penalty --

    def test_calculate_penalty_pytest_fail(self, tmp_path):
        """pytest_fail deve retornar penalidade negativa."""
        provider = self._make_provider(tmp_path)
        penalty = provider.calculate_penalty(action_type="pytest_fail")
        assert penalty == -5.0

    def test_calculate_penalty_with_errors(self, tmp_path):
        """Erros críticos devem ampliar penalidade."""
        provider = self._make_provider(tmp_path)
        penalty_base = provider.calculate_penalty(action_type="pytest_fail")
        penalty_with_errors = provider.calculate_penalty(errors_introduced=2, action_type="pytest_fail")
        assert penalty_with_errors < penalty_base

    # -- record / buffer --

    def test_record_experience_stores_entry(self, tmp_path):
        """record_experience deve adicionar ao replay buffer."""
        provider = self._make_provider(tmp_path)
        provider.record_experience(
            state={"cpu": 10.0},
            action_type="pytest_pass",
            reward=10.0,
        )
        assert len(provider._replay_buffer) == 1
        entry = provider._replay_buffer[0]
        assert entry["action_type"] == "pytest_pass"
        assert entry["reward"] == 10.0

    def test_get_replay_buffer_returns_recent(self, tmp_path):
        """get_replay_buffer deve retornar as entradas mais recentes."""
        provider = self._make_provider(tmp_path)
        for i in range(5):
            provider.record_experience(state={}, action_type=f"action_{i}", reward=float(i))
        buf = provider.get_replay_buffer(limit=3)
        assert len(buf) == 3

    def test_get_cumulative_reward(self, tmp_path):
        """get_cumulative_reward deve somar os rewards recentes."""
        provider = self._make_provider(tmp_path)
        provider.record_experience(state={}, action_type="a", reward=10.0)
        provider.record_experience(state={}, action_type="b", reward=5.0)
        total = provider.get_cumulative_reward(last_n=2)
        assert total == 15.0

    # -- execute() dispatch --

    def test_execute_reward_action_legacy(self, tmp_path):
        """execute() com action_type → usa cálculo legado."""
        provider = self._make_provider(tmp_path)
        result = provider.execute({"action": "reward", "action_type": "pytest_pass"})
        assert result["success"] is True
        assert result["reward"] == 10.0

    def test_execute_reward_action_metrics(self, tmp_path):
        """execute() com before_state/after_state → usa métricas reais."""
        provider = self._make_provider(tmp_path)
        result = provider.execute({
            "action": "reward",
            "before_state": {"tests_passing_rate": 1.0, "avg_latency_ms": 200, "error_rate_24h": 0.0},
            "after_state": {"tests_passing_rate": 1.0, "avg_latency_ms": 200, "error_rate_24h": 0.0},
            "human_approval": True,
        })
        assert result["success"] is True
        assert 0.0 <= result["reward"] <= 1.0

    def test_execute_penalty_action(self, tmp_path):
        """execute() com action='penalty' deve retornar penalidade."""
        provider = self._make_provider(tmp_path)
        result = provider.execute({"action": "penalty", "action_type": "pytest_fail"})
        assert result["success"] is True
        assert result["penalty"] < 0

    def test_execute_record_action(self, tmp_path):
        """execute() com action='record' deve persistir experiência."""
        provider = self._make_provider(tmp_path)
        result = provider.execute({
            "action": "record",
            "state": {},
            "action_type": "deploy_success",
            "reward": 50.0,
        })
        assert result["success"] is True
        assert result["recorded"] is True

    def test_execute_buffer_action(self, tmp_path):
        """execute() com action='buffer' deve retornar lista."""
        provider = self._make_provider(tmp_path)
        result = provider.execute({"action": "buffer", "limit": 10})
        assert result["success"] is True
        assert isinstance(result["buffer"], list)


# ---------------------------------------------------------------------------
# SafetyGuardian
# ---------------------------------------------------------------------------

class TestSafetyGuardian:
    """Tests for SafetyGuardian domain service."""

    def _make_guardian(self, tmp_path):
        from app.domain.services.safety_guardian import SafetyGuardian
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            guardian = SafetyGuardian.__new__(SafetyGuardian)
            guardian._policies = {}
            guardian._quotas = {
                "max_api_calls_per_minute": 60,
                "max_compute_seconds_per_task": 300,
                "max_storage_write_mb": 500,
            }
            guardian._emergency_tokens = ["valid_token_123"]
            guardian._emergency_stop_active = False
            import time
            guardian._resource_counters = {
                "api_calls_this_minute": 0.0,
                "api_window_start": time.time(),
                "compute_seconds_running": 0.0,
                "storage_written_mb": 0.0,
            }
            return guardian

    def test_validate_action_allows_safe_action(self, tmp_path):
        """Ação segura deve ser permitida."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            allowed, reason = guardian.validate_action("read_file")
        assert allowed is True
        assert reason == "allowed"

    def test_validate_action_blocks_high_risk_without_approval(self, tmp_path):
        """Ação de alto risco sem aprovação explícita deve ser bloqueada."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            allowed, reason = guardian.validate_action("delete_file")
        assert allowed is False
        assert "high_risk_action_requires_approval" in reason

    def test_validate_action_allows_high_risk_with_approval(self, tmp_path):
        """Ação de alto risco com aprovação explícita deve ser permitida."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            allowed, reason = guardian.validate_action(
                "delete_file", action_context={"explicit_approval": True}
            )
        assert allowed is True

    def test_validate_action_blocked_during_emergency_stop(self, tmp_path):
        """Qualquer ação deve ser bloqueada durante emergency stop ativo."""
        guardian = self._make_guardian(tmp_path)
        guardian._emergency_stop_active = True
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            allowed, reason = guardian.validate_action("read_file")
        assert allowed is False
        assert "emergency_stop_active" in reason

    def test_custom_policy_blocks_action(self, tmp_path):
        """Política customizada deve bloquear ação listada."""
        guardian = self._make_guardian(tmp_path)
        guardian._policies = {
            "no_external_calls": {"blocked_actions": ["external_api_call"]}
        }
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            allowed, reason = guardian.validate_action("external_api_call")
        assert allowed is False
        assert "policy_blocked" in reason

    def test_check_resource_quota_within_limits(self, tmp_path):
        """Uso de recursos dentro das quotas deve ser permitido."""
        guardian = self._make_guardian(tmp_path)
        ok, reason = guardian.check_resource_quota({"api_calls": 5, "compute_s": 10})
        assert ok is True
        assert reason == "ok"

    def test_check_resource_quota_exceeds_api(self, tmp_path):
        """Exceder quota de API deve retornar False."""
        guardian = self._make_guardian(tmp_path)
        guardian._resource_counters["api_calls_this_minute"] = 55.0
        ok, reason = guardian.check_resource_quota({"api_calls": 10})
        assert ok is False
        assert "quota_exceeded" in reason

    def test_emergency_stop_with_valid_token(self, tmp_path):
        """Token válido deve ativar/desativar emergency stop."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            result = guardian.emergency_stop_protocol("valid_token_123")
        assert result["activated"] is True

    def test_emergency_stop_with_invalid_token(self, tmp_path):
        """Token inválido não deve alterar estado de emergency stop."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            result = guardian.emergency_stop_protocol("wrong_token")
        assert result["activated"] is False
        assert guardian._emergency_stop_active is False

    def test_execute_validate_action(self, tmp_path):
        """execute() deve delegar para validate_action."""
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", tmp_path / "audit.jsonl"):
            result = guardian.execute({"action_type": "read_file", "action_context": {}})
        assert result["success"] is True
        assert result["allowed"] is True

    def test_audit_log_written(self, tmp_path):
        """Toda decisão via execute() deve ser registrada no audit log."""
        audit_file = tmp_path / "audit.jsonl"
        guardian = self._make_guardian(tmp_path)
        with patch("app.domain.services.safety_guardian._AUDIT_LOG_FILE", audit_file):
            guardian.execute({"action_type": "read_file", "action_context": {}})
        assert audit_file.exists()
        line = audit_file.read_text().strip().splitlines()[0]
        entry = json.loads(line)
        assert "action_type" in entry
        assert "allowed" in entry


# ---------------------------------------------------------------------------
# ModelOrchestrator
# ---------------------------------------------------------------------------

class TestModelOrchestrator:
    """Tests for ModelOrchestrator application service."""

    def _make_orchestrator(self):
        from collections import OrderedDict
        from app.application.services.model_orchestrator import ModelOrchestrator
        orch = ModelOrchestrator.__new__(ModelOrchestrator)
        orch._response_cache = OrderedDict()
        return orch

    def test_execute_requires_prompt(self):
        """execute() sem prompt deve retornar success=False."""
        orch = self._make_orchestrator()
        result = orch.execute({})
        assert result["success"] is False
        assert "prompt" in result["error"]

    def test_select_model_fast(self):
        """Perfil 'fast' deve retornar modelo llama."""
        from app.application.services.model_orchestrator import _MODEL_FAST
        orch = self._make_orchestrator()
        model = orch._select_model("fast")
        assert model == _MODEL_FAST

    def test_select_model_reasoning(self):
        """Perfil 'reasoning' deve retornar modelo qwen."""
        from app.application.services.model_orchestrator import _MODEL_REASONING
        orch = self._make_orchestrator()
        model = orch._select_model("reasoning")
        assert model == _MODEL_REASONING

    def test_cache_stores_and_retrieves(self):
        """Cache deve armazenar e recuperar respostas."""
        orch = self._make_orchestrator()
        result = {"success": True, "response": "test", "provider": "ollama"}
        orch._set_cached("hello", "fast", result)
        cached = orch._get_cached("hello", "fast")
        assert cached is not None
        assert cached["response"] == "test"

    def test_cache_different_keys(self):
        """Prompts diferentes devem ter entradas de cache distintas."""
        orch = self._make_orchestrator()
        result = {"success": True, "response": "r1", "provider": "ollama"}
        orch._set_cached("prompt1", "fast", result)
        assert orch._get_cached("prompt2", "fast") is None

    def test_fallback_cloud_when_ollama_fails(self):
        """Quando Ollama falha, deve usar fallback cloud."""
        orch = self._make_orchestrator()
        mock_gateway = MagicMock()
        mock_gateway.execute.return_value = {
            "success": True, "response": "cloud response", "provider": "gemini"
        }

        with patch("app.application.services.model_orchestrator.nexus") as mock_nexus:
            mock_nexus.resolve.side_effect = lambda name: (
                None if name == "ollama_adapter" else mock_gateway
            )
            result = orch.execute({"prompt": "test", "use_cache": False})

        assert result["success"] is True

    def test_execute_uses_ollama_when_available(self):
        """Quando Ollama está disponível, deve usá-lo."""
        orch = self._make_orchestrator()
        mock_ollama = MagicMock()
        mock_ollama.execute.return_value = {
            "success": True, "response": "local response", "provider": "ollama"
        }

        with patch("app.application.services.model_orchestrator.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_ollama
            result = orch.execute({"prompt": "test", "use_cache": False})

        assert result["success"] is True
        assert result["provider"] == "ollama"
