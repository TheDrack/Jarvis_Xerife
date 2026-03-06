# -*- coding: utf-8 -*-
"""Tests for EvolutionSandbox (Etapa 8)."""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.evolution_sandbox import EvolutionSandbox, _check_syntax


@pytest.fixture
def sandbox(tmp_path):
    sb = EvolutionSandbox()
    sb.sandbox_base = tmp_path / "sandbox"
    return sb


class TestEvolutionSandboxInit:
    def test_defaults(self, sandbox):
        assert sandbox.timeout == 120
        assert sandbox.sandbox_base.name == "sandbox"

    def test_enabled_by_default(self, sandbox):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SANDBOX_ENABLED", None)
            assert sandbox.enabled is True

    def test_disabled_via_env(self, sandbox):
        with patch.dict(os.environ, {"SANDBOX_ENABLED": "false"}):
            sandbox._enabled = None  # reset cache
            assert sandbox.enabled is False

    def test_configure_enables_disable(self, sandbox):
        sandbox.configure({"enabled": False})
        assert sandbox.enabled is False
        sandbox.configure({"enabled": True})
        assert sandbox.enabled is True


class TestSandboxDisabled:
    def test_disabled_sandbox_always_passes(self, sandbox):
        """Quando SANDBOX_ENABLED=false, deve retornar passed=True sem executar testes."""
        sandbox.configure({"enabled": False})
        result = sandbox.test_proposal("def invalid(:", "")
        assert result["passed"] is True
        assert result["test_output"] == "sandbox_disabled"
        assert result["errors"] == []

    def test_execute_with_disabled_sandbox(self, sandbox):
        """execute() com sandbox desabilitado retorna success=True."""
        sandbox.configure({"enabled": False})
        result = sandbox.execute({"proposal_code": "def x(): pass"})
        assert result["success"] is True


class TestSandboxSyntaxValidation:
    def test_syntax_error_detected_before_pytest(self, sandbox):
        """Proposta com erro de sintaxe deve falhar antes de executar pytest."""
        sandbox.configure({"enabled": True})
        result = sandbox.test_proposal("def broken(:\n    pass", "")
        assert result["passed"] is False
        assert any("sintaxe" in e.lower() or "syntax" in e.lower() for e in result["errors"])

    def test_valid_syntax_proceeds(self, sandbox):
        """Proposta com sintaxe válida deve prosseguir para execução de testes."""
        sandbox.configure({"enabled": True})
        # Mock subprocess para evitar execução real de pytest
        with patch("app.application.services.evolution_sandbox.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")
            result = sandbox.test_proposal("def valid(): return True", "")
        assert result["passed"] is True


class TestCheckSyntax:
    def test_valid_code_returns_none(self):
        assert _check_syntax("def hello():\n    return True") is None

    def test_invalid_code_returns_message(self):
        error = _check_syntax("def broken(:\n    pass")
        assert error is not None
        assert len(error) > 0

    def test_empty_code_is_valid_syntax(self):
        """Código vazio é sintaticamente válido."""
        assert _check_syntax("") is None


class TestSandboxCleanup:
    def test_sandbox_dir_cleaned_on_success(self, sandbox, tmp_path):
        """Diretório temporário deve ser removido após execução bem-sucedida."""
        sandbox.configure({"enabled": True})
        sandbox.sandbox_base = tmp_path / "sandboxes"

        with patch("app.application.services.evolution_sandbox.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="passed", stderr="")
            sandbox.test_proposal("def ok(): pass", "")

        # O diretório base pode existir mas nenhum subdiretório deve ter restado
        remaining = list(sandbox.sandbox_base.glob("*/")) if sandbox.sandbox_base.exists() else []
        assert len(remaining) == 0

    def test_sandbox_dir_cleaned_on_failure(self, sandbox, tmp_path):
        """Diretório temporário deve ser removido mesmo após falha de sintaxe."""
        sandbox.configure({"enabled": True})
        sandbox.sandbox_base = tmp_path / "sandboxes"

        sandbox.test_proposal("def broken(:\n    pass", "")

        remaining = list(sandbox.sandbox_base.glob("*/")) if sandbox.sandbox_base.exists() else []
        assert len(remaining) == 0


class TestSandboxGatekeeperIntegration:
    def test_gatekeeper_calls_sandbox(self):
        """EvolutionGatekeeper deve consultar o EvolutionSandbox como 5ª verificação."""
        from app.application.services.evolution_gatekeeper import EvolutionGatekeeper

        gatekeeper = EvolutionGatekeeper()

        mock_sandbox = MagicMock()
        mock_sandbox.test_proposal.return_value = {"passed": True, "test_output": "", "errors": []}

        with patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            def resolve(name):
                if name == "evolution_sandbox":
                    return mock_sandbox
                return None

            mock_nexus.resolve.side_effect = resolve

            proposed = {
                "files_modified": [],
                "proposed_code": "def safe(): return True",
            }
            # Mock as primeiras 4 verificações para passar
            with patch.object(gatekeeper, "_check_test_count", return_value=(True, "ok")):
                with patch.object(gatekeeper, "_check_recent_stability", return_value=(True, "ok")):
                    approved, reason = gatekeeper.approve_evolution(proposed)

        # O sandbox foi consultado
        mock_sandbox.test_proposal.assert_called_once()
        assert approved is True

    def test_gatekeeper_blocks_when_sandbox_fails(self):
        """Gatekeeper deve bloquear quando o sandbox reporta falha."""
        from app.application.services.evolution_gatekeeper import EvolutionGatekeeper

        gatekeeper = EvolutionGatekeeper()

        mock_sandbox = MagicMock()
        mock_sandbox.test_proposal.return_value = {
            "passed": False,
            "test_output": "FAILED tests/",
            "errors": ["pytest retornou código 1"],
        }

        with patch("app.application.services.evolution_gatekeeper.nexus") as mock_nexus:
            def resolve(name):
                if name == "evolution_sandbox":
                    return mock_sandbox
                return None

            mock_nexus.resolve.side_effect = resolve

            proposed = {
                "files_modified": [],
                "proposed_code": "def breaks_tests(): raise RuntimeError()",
            }
            with patch.object(gatekeeper, "_check_test_count", return_value=(True, "ok")):
                with patch.object(gatekeeper, "_check_recent_stability", return_value=(True, "ok")):
                    approved, reason = gatekeeper.approve_evolution(proposed)

        assert approved is False
        assert "sandbox_failed" in reason
