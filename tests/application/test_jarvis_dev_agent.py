# -*- coding: utf-8 -*-
"""Tests for JarvisDevAgent (Etapa 7)."""
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.jarvis_dev_agent import JarvisDevAgent, _extract_code_block


@pytest.fixture
def agent():
    return JarvisDevAgent()


class TestJarvisDevAgentInit:
    def test_defaults(self, agent):
        assert agent.max_few_shot == 3
        assert agent.dry_run is False

    def test_configure(self, agent):
        agent.configure({"max_few_shot": 5, "dry_run": True})
        assert agent.max_few_shot == 5
        assert agent.dry_run is True


class TestJarvisDevAgentNoCapability:
    def test_execute_returns_failure_when_no_capability(self, agent):
        """Quando não há capabilities executáveis, retorna falha."""
        with patch("app.application.services.jarvis_dev_agent.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            result = agent.execute({})
        assert result["success"] is False
        assert result["reason"] == "no_executable_capability"

    def test_can_execute_returns_false_when_no_capability(self, agent):
        """can_execute retorna False quando não há capability disponível."""
        with patch("app.application.services.jarvis_dev_agent.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = None
            assert agent.can_execute({}) is False


class TestJarvisDevAgentCapabilitySelection:
    def test_selects_first_executable_capability(self, agent):
        """Deve selecionar a primeira capability retornada pelo CapabilityManager."""
        cap_manager = MagicMock()
        cap_manager.get_executable_capabilities.return_value = [
            {"id": "CAP-001", "title": "Test Cap"},
            {"id": "CAP-002", "title": "Other Cap"},
        ]
        agent.dry_run = True

        with patch("app.application.services.jarvis_dev_agent.nexus") as mock_nexus:
            def resolve(name):
                if name == "capability_manager":
                    return cap_manager
                return None

            mock_nexus.resolve.side_effect = resolve

            result = agent.execute({})

        # Deve ter tentado selecionar a capability
        cap_manager.get_executable_capabilities.assert_called_once()


class TestJarvisDevAgentPromptWithMemory:
    def test_builds_prompt_with_few_shot_context(self, agent):
        """O prompt deve incluir exemplos da SemanticMemory como contexto few-shot."""
        cap = {"id": "CAP-042", "title": "Test Feature", "description": "Implementar algo"}
        few_shot = [
            {"fact_type": "solution", "content": "Solução A", "confidence": 0.9},
            {"fact_type": "solution", "content": "Solução B", "confidence": 0.8},
        ]

        prompt = agent._build_prompt(cap, few_shot)

        assert "CAP-042" in prompt
        assert "Test Feature" in prompt
        assert "Solução A" in prompt
        assert "Solução B" in prompt
        assert "NexusComponent" in prompt

    def test_builds_prompt_without_few_shot(self, agent):
        """O prompt deve funcionar sem exemplos da memória."""
        cap = {"id": "CAP-001", "title": "Basic Cap"}
        prompt = agent._build_prompt(cap, [])
        assert "CAP-001" in prompt
        assert "NexusComponent" in prompt
        assert "Exemplo" not in prompt


class TestJarvisDevAgentGatekeeperRejection:
    def test_gatekeeper_rejection_stops_cycle(self, agent):
        """Quando o Gatekeeper rejeita, não deve criar PR."""
        cap_manager = MagicMock()
        cap_manager.get_executable_capabilities.return_value = [
            {"id": "CAP-099", "title": "Risky Cap"}
        ]

        router = MagicMock()
        router.execute.return_value = {
            "success": True,
            "result": "```python\ndef risky(): pass\n```",
            "routed_to": "ollama_adapter",
        }

        gatekeeper = MagicMock()
        gatekeeper.approve_evolution.return_value = (False, "tests_would_break")

        memory = MagicMock()
        memory.query_facts.return_value = []

        with patch("app.application.services.jarvis_dev_agent.nexus") as mock_nexus:
            def resolve(name):
                if name == "capability_manager":
                    return cap_manager
                if name == "llm_router":
                    return router
                if name == "evolution_gatekeeper":
                    return gatekeeper
                if name == "semantic_memory":
                    return memory
                return None

            mock_nexus.resolve.side_effect = resolve

            agent.dry_run = True  # não toca em disco
            result = agent.execute({})

        assert result["success"] is False
        assert "tests_would_break" in result.get("reason", "")
        assert result.get("gatekeeper_result", {}).get("approved") is False


class TestJarvisDevAgentSuccessFlow:
    def test_full_success_flow(self, agent, tmp_path):
        """Ciclo completo bem-sucedido: capability → LLM → Gatekeeper → PR."""
        import app.application.services.jarvis_dev_agent as dev_mod

        original_proposals = dev_mod._PROPOSALS_DIR
        dev_mod._PROPOSALS_DIR = tmp_path / "proposals"

        try:
            cap_manager = MagicMock()
            cap_manager.get_executable_capabilities.return_value = [
                {"id": "CAP-007", "title": "Automate Tests"}
            ]

            router = MagicMock()
            router.execute.return_value = {
                "success": True,
                "result": "```python\ndef automate(): return True\n```",
                "routed_to": "ollama_adapter",
            }

            gatekeeper = MagicMock()
            gatekeeper.approve_evolution.return_value = (True, "approved")

            worker = MagicMock()
            worker.submit_pull_request.return_value = {"success": True, "pr_url": "http://pr"}

            memory = MagicMock()
            memory.query_facts.return_value = []

            with patch("app.application.services.jarvis_dev_agent.nexus") as mock_nexus:
                def resolve(name):
                    if name == "capability_manager":
                        return cap_manager
                    if name == "llm_router":
                        return router
                    if name == "evolution_gatekeeper":
                        return gatekeeper
                    if name == "github_worker":
                        return worker
                    if name == "semantic_memory":
                        return memory
                    return None

                mock_nexus.resolve.side_effect = resolve

                result = agent.execute({})
        finally:
            dev_mod._PROPOSALS_DIR = original_proposals

        assert result["success"] is True
        assert result["capability_id"] == "CAP-007"
        assert result["pr_created"] is True

        # Verifica que a proposta foi salva
        proposals = list((tmp_path / "proposals").glob("*_dev_agent.py"))
        assert len(proposals) == 1


class TestExtractCodeBlock:
    def test_extracts_python_fence(self):
        text = "Aqui vai o código:\n```python\ndef hello():\n    pass\n```\nFim."
        assert _extract_code_block(text) == "def hello():\n    pass"

    def test_extracts_generic_fence(self):
        text = "```\ndef world():\n    pass\n```"
        assert _extract_code_block(text) == "def world():\n    pass"

    def test_returns_raw_when_no_fence(self):
        text = "def raw(): pass"
        assert _extract_code_block(text) == "def raw(): pass"

    def test_opening_fence_without_closing(self):
        """Quando não há fence de fechamento, retorna o texto após a abertura."""
        text = "```python\ndef unclosed():\n    pass"
        result = _extract_code_block(text)
        assert "def unclosed" in result
