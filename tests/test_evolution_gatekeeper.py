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
    """Testa verificação (a): contagem de testes."""

    def test_approves_when_count_stable(self):
        """Deve aprovar quando a contagem de testes não regrediu."""
        gk = EvolutionGatekeeper()
        # Simula retorno do pytest --co -q
        mock_result = MagicMock()
        mock_result.stdout = "350 tests collected\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            ok, reason = gk._check_test_count()
        assert ok is True
        assert gk._last_test_count == 350

    def test_blocks_when_count_regresses(self):
        """Deve bloquear quando a contagem de testes regrediu."""
        gk = EvolutionGatekeeper()
        gk._last_test_count = 350

        mock_result = MagicMock()
        mock_result.stdout = "300 tests collected\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            ok, reason = gk._check_test_count()
        assert ok is False
        assert "test_regression" in reason

    def test_approves_on_pytest_not_found(self):
        """Deve permitir se pytest não está instalado."""
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, reason = gk._check_test_count()
        assert ok is True

    def test_approves_on_timeout(self):
        """Deve permitir em caso de timeout."""
        gk = EvolutionGatekeeper()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 60)):
            ok, reason = gk._check_test_count()
        assert ok is True


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

    def test_approves_with_override(self):
        """Com gatekeeper_override=True, deve aprovar mudanças no núcleo."""
        gk = EvolutionGatekeeper()
        change = {
            "files_modified": ["app/core/nexus.py"],
            "gatekeeper_override": True,
        }
        ok, reason = gk._check_core_protection(change)
        assert ok is True

    def test_approves_non_core_file(self):
        """Deve aprovar mudança em arquivo fora do núcleo."""
        gk = EvolutionGatekeeper()
        change = {"files_modified": ["app/application/services/llm_router.py"]}
        ok, reason = gk._check_core_protection(change)
        assert ok is True


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

        with patch("subprocess.run", return_value=mock_result), \
             patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None  # audit_logger e evolution_loop indisponíveis
            approved, reason = gk.approve_evolution(proposed)

        assert approved is True
        assert reason == "approved"

    def test_blocks_when_frozen_file_in_change(self):
        """Deve bloquear quando há arquivo frozen na mudança proposta."""
        gk = EvolutionGatekeeper()
        proposed = {"files_modified": [".frozen/old_module.py"]}

        mock_result = MagicMock()
        mock_result.stdout = "400 tests collected\n"
        mock_result.stderr = ""

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
