# -*- coding: utf-8 -*-
"""Tests for EvolutionOrchestrator — MELHORIA 1."""
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.evolution_orchestrator import EvolutionOrchestrator


@pytest.fixture
def orchestrator():
    return EvolutionOrchestrator()


class TestEvolutionOrchestratorInit:
    def test_defaults(self, orchestrator):
        assert orchestrator.max_cycles == 3
        assert orchestrator.auto_apply is False
        assert orchestrator.target_area == ""

    def test_configure(self, orchestrator):
        orchestrator.configure({"max_cycles": 5, "auto_apply": True, "target_area": "app/adapters"})
        assert orchestrator.max_cycles == 5
        assert orchestrator.auto_apply is True
        assert orchestrator.target_area == "app/adapters"


class TestEvolutionOrchestratorCycleLimit:
    def test_max_cycles_reached_returns_failure(self, orchestrator):
        orchestrator.configure({"max_cycles": 0})
        result = orchestrator.execute({})
        assert result["success"] is False
        assert result["reason"] == "max_cycles_reached"

    def test_respects_max_cycles(self, orchestrator):
        orchestrator.configure({"max_cycles": 1})
        # First call should proceed (not limit out), second should limit
        with patch.object(orchestrator, "_run_cycle", return_value={"success": True}):
            r1 = orchestrator.execute({})
        assert r1["success"] is True
        r2 = orchestrator.execute({})
        assert r2["success"] is False
        assert r2["reason"] == "max_cycles_reached"


class TestEvolutionOrchestratorSuccessFlow:
    def test_valid_patch_creates_proposal_and_pr(self, orchestrator, tmp_path):
        """Fluxo de sucesso: patch válido deve ser salvo e PR criado."""
        valid_code = '"""Mudança de teste."""\n\ndef hello():\n    return "world"\n'

        mock_worker = MagicMock()
        mock_worker.submit_pull_request.return_value = {"success": True, "pr_url": "http://pr"}
        mock_metabolism = MagicMock()
        mock_metabolism.execute.return_value = {"success": True, "result": f"```python\n{valid_code}```"}

        import app.application.services.evolution_orchestrator as evo_mod

        original_proposals = evo_mod._PROPOSALS_DIR
        evo_mod._PROPOSALS_DIR = tmp_path / "proposals"

        try:
            with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
                def resolve(name):
                    if name == "metabolism_core":
                        return mock_metabolism
                    if name == "github_worker":
                        return mock_worker
                    return None

                mock_nexus.resolve.side_effect = resolve

                result = orchestrator.execute({"error_snippet": "some error"})

        finally:
            evo_mod._PROPOSALS_DIR = original_proposals

        assert result["success"] is True
        assert result["source"] == "llm"
        assert "proposal" in result


class TestEvolutionOrchestratorFailureFlow:
    def test_invalid_patch_registers_in_thought_log(self, orchestrator):
        """Fluxo de falha: patch inválido deve registrar no ThoughtLog."""
        invalid_code = "def broken(:\n    pass"

        mock_metabolism = MagicMock()
        mock_metabolism.execute.return_value = {
            "success": True,
            "result": f"```python\n{invalid_code}```",
        }
        mock_tls = MagicMock()

        with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
            def resolve(name):
                if name == "metabolism_core":
                    return mock_metabolism
                if name == "thought_log_service":
                    return mock_tls
                return None

            mock_nexus.resolve.side_effect = resolve

            result = orchestrator.execute({"error_snippet": "some error"})

        assert result["success"] is False
        assert result["reason"] == "invalid_syntax"
        mock_tls.create_thought.assert_called_once()
        call_kwargs = mock_tls.create_thought.call_args.kwargs
        assert call_kwargs.get("success") is False


class TestEvolutionOrchestratorProceduralMemory:
    def test_uses_procedural_memory_when_available(self, orchestrator):
        """Se a memória procedural retornar solução, deve usá-la sem chamar o LLM."""
        mock_mem = MagicMock()
        mock_mem.search_solution.return_value = {
            "solution_attempt": "# cached solution",
            "score": 0.95,
        }
        mock_tls = MagicMock()

        with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
            def resolve(name):
                if name == "procedural_memory_adapter":
                    return mock_mem
                if name == "thought_log_service":
                    return mock_tls
                return None

            mock_nexus.resolve.side_effect = resolve

            result = orchestrator.execute({"error_snippet": "NullPointerError"})

        assert result["success"] is True
        assert result["source"] == "procedural_memory"
        mock_mem.search_solution.assert_called_once_with("NullPointerError")


class TestEvolutionOrchestratorFullCycle:
    """Etapa 6.6 — Teste de integração: ciclo completo com MetaReflection + Gatekeeper."""

    def test_full_cycle_meta_reflection_injected_gatekeeper_approves(self, orchestrator, tmp_path):
        """Ciclo completo: MetaReflection injetada → Gatekeeper aprovando → proposta gerada."""
        valid_code = '"""Ciclo completo."""\n\ndef evolve():\n    return True\n'
        meta_ctx = {"insights": ["JARVIS está estável", "Focar em capabilities de rede"]}

        mock_gatekeeper = MagicMock()
        mock_gatekeeper.approve_evolution.return_value = (True, "approved")

        mock_metabolism = MagicMock()
        mock_metabolism.execute.return_value = {"success": True, "result": f"```python\n{valid_code}```"}

        mock_worker = MagicMock()
        mock_worker.submit_pull_request.return_value = {"success": True, "pr_url": "http://pr"}

        import app.application.services.evolution_orchestrator as evo_mod

        original_proposals = evo_mod._PROPOSALS_DIR
        evo_mod._PROPOSALS_DIR = tmp_path / "proposals"

        try:
            with patch.object(orchestrator, "_load_meta_reflection", return_value=meta_ctx):
                with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
                    def resolve(name):
                        if name == "evolution_gatekeeper":
                            return mock_gatekeeper
                        if name == "metabolism_core":
                            return mock_metabolism
                        if name == "github_worker":
                            return mock_worker
                        return None

                    mock_nexus.resolve.side_effect = resolve

                    result = orchestrator.execute({"error_snippet": "gap a implementar"})
        finally:
            evo_mod._PROPOSALS_DIR = original_proposals

        # Verifica que o ciclo foi bem-sucedido
        assert result["success"] is True
        assert result["source"] == "llm"

        # Verifica que o Gatekeeper foi consultado
        mock_gatekeeper.approve_evolution.assert_called_once()

        # Verifica que a proposta foi salva em data/evolution_proposals/
        proposals_dir = tmp_path / "proposals"
        proposal_files = list(proposals_dir.glob("*.py"))
        assert len(proposal_files) == 1
        content = proposal_files[0].read_text(encoding="utf-8")
        assert "evolve" in content

    def test_gatekeeper_rejection_escalates_to_commander(self, orchestrator):
        """Quando o Gatekeeper rejeita, deve escalar para COMMANDER_NEEDED."""
        mock_gatekeeper = MagicMock()
        mock_gatekeeper.approve_evolution.return_value = (False, "tests_regressed")

        mock_metabolism = MagicMock()

        with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
            def resolve(name):
                if name == "evolution_gatekeeper":
                    return mock_gatekeeper
                if name == "metabolism_core":
                    return mock_metabolism
                return None

            mock_nexus.resolve.side_effect = resolve

            result = orchestrator.execute({})

        assert result["success"] is False
        assert "gatekeeper_blocked" in result["reason"]

    def test_capability_selected_via_capability_manager(self, orchestrator, tmp_path):
        """Verifica que a capability-alvo é selecionada via CapabilityManager."""
        valid_code = '"""Cap via CapabilityManager."""\ndef run(): pass\n'

        mock_cap_manager = MagicMock()
        mock_cap_manager.get_executable_capabilities.return_value = [
            {"id": "CAP-042", "title": "Autonomous test capability"}
        ]

        mock_metabolism = MagicMock()
        mock_metabolism.execute.return_value = {"success": True, "result": f"```python\n{valid_code}```"}

        mock_worker = MagicMock()
        mock_worker.submit_pull_request.return_value = {"success": True}

        import app.application.services.evolution_orchestrator as evo_mod

        original_proposals = evo_mod._PROPOSALS_DIR
        evo_mod._PROPOSALS_DIR = tmp_path / "proposals"

        try:
            with patch("app.application.services.evolution_orchestrator.nexus") as mock_nexus:
                def resolve(name):
                    if name == "capability_manager":
                        return mock_cap_manager
                    if name == "metabolism_core":
                        return mock_metabolism
                    if name == "github_worker":
                        return mock_worker
                    return None

                mock_nexus.resolve.side_effect = resolve

                result = orchestrator.execute({})
        finally:
            evo_mod._PROPOSALS_DIR = original_proposals

        assert result["success"] is True
        mock_cap_manager.get_executable_capabilities.assert_called_once()
