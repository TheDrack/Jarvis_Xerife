# -*- coding: utf-8 -*-
"""Tests for Consolidator – verifica que o documento gerado é autodidático."""

import os
import tempfile
import pytest
from unittest.mock import patch

from app.adapters.infrastructure.consolidator import Consolidator, DOCS_ORDER


class TestConsolidator:
    """Testes para o Consolidator aprimorado."""

    def _make_context(self):
        return {"metadata": {"pipeline": "test"}, "artifacts": {}}

    def test_execute_returns_success_status(self, tmp_path, monkeypatch):
        """execute() deve retornar status success e atualizar context."""
        monkeypatch.chdir(tmp_path)

        c = Consolidator()
        ctx = self._make_context()
        result = c.execute(ctx)

        assert result["result"]["status"] == "success"
        assert "file_path" in result["result"]
        assert result["artifacts"]["consolidator"]["status"] == "success"

    def test_output_contains_documentation_section(self, tmp_path, monkeypatch):
        """O documento gerado deve conter a seção de documentação setorizada."""
        monkeypatch.chdir(tmp_path)

        # Cria um README fake para ser incluído
        (tmp_path / "README.md").write_text("# JARVIS Test README\nConteúdo de teste.", encoding="utf-8")

        c = Consolidator()
        c.execute(self._make_context())

        content = (tmp_path / c.output_file).read_text(encoding="utf-8")
        assert "SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO" in content
        assert "README.md" in content
        assert "JARVIS Test README" in content

    def test_output_contains_tree_section(self, tmp_path, monkeypatch):
        """O documento gerado deve conter a seção de árvore de diretórios."""
        monkeypatch.chdir(tmp_path)

        c = Consolidator()
        c.execute(self._make_context())

        content = (tmp_path / c.output_file).read_text(encoding="utf-8")
        assert "SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)" in content

    def test_output_contains_code_section(self, tmp_path, monkeypatch):
        """O documento gerado deve conter a seção de conteúdo dos arquivos."""
        monkeypatch.chdir(tmp_path)

        # Cria um arquivo .py fake
        (tmp_path / "example.py").write_text("print('hello')", encoding="utf-8")

        c = Consolidator()
        c.execute(self._make_context())

        content = (tmp_path / c.output_file).read_text(encoding="utf-8")
        assert "SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS" in content
        assert "example.py" in content

    def test_output_section_order(self, tmp_path, monkeypatch):
        """Documentação deve aparecer antes da árvore que deve aparecer antes do código."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "README.md").write_text("# JARVIS", encoding="utf-8")
        (tmp_path / "example.py").write_text("x = 1", encoding="utf-8")

        c = Consolidator()
        c.execute(self._make_context())

        content = (tmp_path / c.output_file).read_text(encoding="utf-8")
        pos_doc = content.index("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO")
        pos_tree = content.index("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)")
        pos_code = content.index("SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS")

        assert pos_doc < pos_tree < pos_code

    def test_docs_order_constant_contains_expected_files(self):
        """DOCS_ORDER deve referenciar os principais arquivos de documentação."""
        assert "README.md" in DOCS_ORDER
        assert any("ARCHITECTURE" in d for d in DOCS_ORDER)
        assert any("NEXUS" in d for d in DOCS_ORDER)
        assert any("STATUS" in d for d in DOCS_ORDER)
        assert any("ARQUIVO_MAP" in d for d in DOCS_ORDER)

    def test_missing_doc_files_are_skipped_gracefully(self, tmp_path, monkeypatch):
        """Arquivos de documentação inexistentes devem ser ignorados sem erro."""
        monkeypatch.chdir(tmp_path)
        # tmp_path não tem nenhum arquivo de docs

        c = Consolidator()
        ctx = self._make_context()
        result = c.execute(ctx)  # não deve lançar exceção

        assert result["result"]["status"] == "success"

    def test_header_contains_how_to_read_instructions(self, tmp_path, monkeypatch):
        """O cabeçalho deve conter instruções de como ler o documento."""
        monkeypatch.chdir(tmp_path)

        c = Consolidator()
        c.execute(self._make_context())

        content = (tmp_path / c.output_file).read_text(encoding="utf-8")
        assert "COMO LER ESTE DOCUMENTO" in content
