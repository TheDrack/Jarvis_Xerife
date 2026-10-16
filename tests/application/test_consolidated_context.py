# -*- coding: utf-8 -*-
"""Testes do carregamento tolerante do contexto consolidado (autoconsciência).

O ``load_consolidated_context`` é o ponto único usado por EvolutionOrchestrator e
JarvisDevAgent para injetar o snapshot do codebase (``CORE_LOGIC_CONSOLIDATED.txt``)
no prompt do LLM. Ele precisa ser resiliente: arquivo ausente, serviço não
registrado ou erro no Nexus não podem interromper o ciclo de evolução.
"""
from unittest.mock import patch

from app.application.services.consolidated_context_service import (
    ConsolidatedContextService,
    load_consolidated_context,
)


class TestLoadConsolidatedContext:
    def test_returns_content_when_file_exists(self, tmp_path):
        path = tmp_path / "CORE_LOGIC_CONSOLIDATED.txt"
        path.write_text("conteudo consolidado", encoding="utf-8")

        with patch(
            "app.core.nexus.nexus.resolve",
            return_value=ConsolidatedContextService(str(path)),
        ):
            assert load_consolidated_context() == "conteudo consolidado"

    def test_truncates_content_above_limit(self, tmp_path):
        path = tmp_path / "CORE_LOGIC_CONSOLIDATED.txt"
        path.write_text("x" * 500, encoding="utf-8")

        with patch(
            "app.core.nexus.nexus.resolve",
            return_value=ConsolidatedContextService(str(path)),
        ):
            content = load_consolidated_context(max_chars=100)

        assert content.startswith("x" * 100)
        assert "truncado" in content
        assert len(content) < 500

    def test_missing_file_returns_empty_string(self, tmp_path):
        service = ConsolidatedContextService(str(tmp_path / "nao_existe.txt"))

        with patch("app.core.nexus.nexus.resolve", return_value=service):
            assert load_consolidated_context() == ""

    def test_unregistered_service_returns_empty_string(self):
        with patch("app.core.nexus.nexus.resolve", return_value=None):
            assert load_consolidated_context() == ""

    def test_nexus_failure_returns_empty_string(self):
        with patch("app.core.nexus.nexus.resolve", side_effect=RuntimeError("boom")):
            assert load_consolidated_context() == ""
