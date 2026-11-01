# -*- coding: utf-8 -*-
"""Tests for EvolutionGatekeeper."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.evolution_gatekeeper import (
    EvolutionGatekeeper,
    _parse_test_count,
)


class TestEvolutionGatekeeperTestCount:
    """A coleta de testes só aprova quando o resultado é verificável."""

    @staticmethod
    def _result(stdout="350 tests collected\\n", stderr="", returncode=0):
        result = MagicMock()
        result.stdout = stdout
        result.stderr = stderr
        result.returncode = returncode
        return result

    def test_approves_when_count_is_stable(self):
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", return_value=self._result()):
            ok, reason = gk._check_test_count()
        assert (ok, reason) == (True, "ok")
        assert gk._last_test_count == 350

    def test_blocks_when_count_regresses_without_overwriting_baseline(self):
        gk = EvolutionGatekeeper()
        gk._last_test_count = 350
        with patch("subprocess.run", return_value=self._result("300 tests collected\\n")):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert "test_regression" in reason
        assert gk._last_test_count == 350

    def test_blocks_when_pytest_is_not_found(self):
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_unavailable"
        assert gk._last_test_count is None

    def test_blocks_on_collection_timeout(self):
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 60)):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_timeout"
        assert gk._last_test_count is None

    def test_blocks_when_pytest_returns_nonzero_even_with_a_count(self):
        gk = EvolutionGatekeeper()
        result = self._result("350 tests collected\\n", "collection error", 1)
        with patch("subprocess.run", return_value=result):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_failed: pytest_exit_code=1"
        assert gk._last_test_count is None

    def test_blocks_when_collection_output_has_no_recognized_count(self):
        gk = EvolutionGatekeeper()
        result = self._result("pytest: internal collection error\\n")
        with patch("subprocess.run", return_value=result):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_unrecognized_or_empty"
        assert gk._last_test_count is None

    def test_blocks_when_collection_reports_zero_tests(self):
        gk = EvolutionGatekeeper()
        result = self._result("0 tests collected\\n")
        with patch("subprocess.run", return_value=result):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_unrecognized_or_empty"
        assert gk._last_test_count is None

    def test_blocks_when_collection_raises_unexpected_error(self):
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", side_effect=RuntimeError("runner unavailable")):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_collection_error: RuntimeError"
        assert gk._last_test_count is None

    def test_blocks_when_count_is_below_configured_minimum(self):
        gk = EvolutionGatekeeper(min_test_count=400)
        with patch("subprocess.run", return_value=self._result("350 tests collected\\n")):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert reason == "test_count_below_minimum: 350 < 400"
        assert gk._last_test_count is None


class TestEvolutionGatekeeperFrozenFiles:
    """Testa verificação (c): proteção de arquivos frozen."""

    def test_blocks_frozen_file(self):
        """Deve bloquear mudança em arquivo .frozen/."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": [".frozen/some_module.py"]}
        ok, reason = gk._check_frozen_files(change)
        assert ok is False
        assert "frozen_file_protected" in reason

    def test_approves_non_frozen_file(self):
        """Deve aprovar mudança em arquivo fora de .frozen/."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": ["app/application/services/llm_router.py"]}
        ok, reason = gk._check_frozen_files(change)
        assert ok is True

    def test_approves_empty_files(self):
        """Deve aprovar quando não há arquivos modificados."""
        gk = EvolutionGatekeeper()
        ok, reason = gk._check_frozen_files({})
        assert ok is True


class TestEvolutionGatekeeperCoreProtection:
    """Testa verificação (d): proteção do núcleo."""

    def test_blocks_core_file(self):
        """Deve bloquear mudança em app/core/nexus.py."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": ["app/core/nexus.py"]}
        ok, reason = gk._check_core_protection(change)
        assert ok is False
        assert "core_file_protected" in reason

    def test_blocks_nexus_registry(self):
        """Deve bloquear mudança em app/core/nexus_registry.py."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": ["app/core/nexus_registry.py"]}
        ok, reason = gk._check_core_protection(change)
        assert ok is False

    def test_legacy_override_cannot_bypass_core_protection(self):
        """O campo legado gatekeeper_override não pode ignorar a proteção do núcleo."""
        gk = EvolutionGatekeeper()
        change = {
            "files_modified": ["app/core/nexus.py"],
            "gatekeeper_override": True,
        }
        ok, reason = gk._check_core_protection(change)
        assert ok is False
        assert "core_file_protected" in reason

    def test_approves_non_core_file(self):
        """Deve aprovar mudança em arquivo fora do núcleo."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": ["app/application/services/llm_router.py"]}
        ok, reason = gk._check_core_protection(change)
        assert ok is True


class TestEvolutionGatekeeperSandboxFailClosed:
    """Propostas de código não podem ser aprovadas sem validação efetiva."""

    def test_blocks_code_proposal_when_sandbox_unavailable(self):
        gk = EvolutionGatekeeper()
        with patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            ok, reason = gk._check_sandbox({"proposed_code": "print('candidate')"})
        assert ok is False
        assert "sandbox_unavailable" in reason

    def test_blocks_code_proposal_when_sandbox_raises(self):
        gk = EvolutionGatekeeper()
        mock_sandbox = MagicMock()
        mock_sandbox.test_proposal.side_effect = RuntimeError("sandbox crashed")
        with patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_sandbox
            ok, reason = gk._check_sandbox({"proposed_code": "print('candidate')"})
        assert ok is False
        assert "sandbox_error" in reason

    def test_metadata_only_change_does_not_require_code_sandbox(self):
        gk = EvolutionGatekeeper()
        ok, reason = gk._check_sandbox({"files_modified": ["docs/README.md"]})
        assert ok is True
        assert reason == "ok"


class TestEvolutionGatekeeperStability:
    """Testa verificação (b): estabilidade recente."""

    def test_approves_when_no_rollback(self):
        """Deve aprovar quando não há rollback recente."""
        gk = EvolutionGatekeeper()
        with patch.object(gk, "_check_recent_stability", return_value=(True, "ok")):
            ok, reason = gk._check_recent_stability()
        assert ok is True

    def test_approves_when_evolution_loop_unavailable(self):
        """Deve aprovar quando evolution_loop não está disponível."""
        gk = EvolutionGatekeeper()
        with patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            ok, reason = gk._check_recent_stability()
        assert ok is True


class TestEvolutionGatekeeperFullFlow:
    """Testa o fluxo completo de aprovação."""

    def test_full_approval_flow(self):
        """Fluxo completo deve aprovar quando todas as verificações passam."""
        gk = EvolutionGatekeeper()
        proposed = {"files_modified": ["app/application/services/new_feature.py"]}

        mock_result = MagicMock()
        mock_result.stdout = "400 tests collected\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result), \
             patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None  # audit_logger e evolution_loop indisponíveis
            approved, reason = gk.approve_evolution(proposed)

        assert approved is True
        assert reason == "approved"

    def test_approve_calls_reward_signal_provider(self):
        """Ao aprovar, deve chamar calculate_reward no RewardSignalProvider."""
        gk = EvolutionGatekeeper()
        proposed = {
            "files_modified": ["app/application/services/new_feature.py"],
            "before_state": {"tests_passing_rate": 0.9},
            "after_state": {"tests_passing_rate": 1.0},
        }

        mock_result = MagicMock()
        mock_result.stdout = "400 tests collected\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        mock_reward_provider = MagicMock()
        mock_reward_provider.calculate_reward.return_value = 0.9

        def _resolve(name):
            if name == "reward_signal_provider":
                return mock_reward_provider
            return None

        with patch("subprocess.run", return_value=mock_result), \
             patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.side_effect = _resolve
            approved, reason = gk.approve_evolution(proposed)

        assert approved is True
        mock_reward_provider.calculate_reward.assert_called_once_with(
            before_state={"tests_passing_rate": 0.9},
            after_state={"tests_passing_rate": 1.0},
            human_approval=True,
        )

    def test_blocks_when_frozen_file_in_change(self):
        """Deve bloquear quando há arquivo frozen na mudança proposta."""
        gk = EvolutionGatekeeper()
        proposed = {"files_modified": [".frozen/old_module.py"]}

        mock_result = MagicMock()
        mock_result.stdout = "400 tests collected\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result), \
             patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            approved, reason = gk.approve_evolution(proposed)

        assert approved is False
        assert "frozen" in reason

    def test_execute_interface(self):
        """execute() deve retornar dicionário com campo approved."""
        gk = EvolutionGatekeeper()

        mock_result = MagicMock()
        mock_result.stdout = "300 tests collected\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result), \
             patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            result = gk.execute({"proposed_change": {"files_modified": []}})

        assert "approved" in result
        assert "reason" in result
        assert result["success"] is True


class TestParseTestCount:
    """Testa o helper _parse_test_count."""

    def test_parses_standard_format(self):
        assert _parse_test_count("350 tests collected") == 350

    def test_parses_singular(self):
        assert _parse_test_count("1 test collected") == 1

    def test_returns_zero_when_no_match(self):
        assert _parse_test_count("no tests found") == 0

    def test_handles_complex_output(self):
        output = (
            "collecting ... \n"
            "collected 42 tests\n"
            "========================\n"
        )
        assert _parse_test_count(output) == 42
