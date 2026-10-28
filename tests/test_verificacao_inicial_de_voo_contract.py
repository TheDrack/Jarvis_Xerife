"""Regression contract for the mandatory Verificação Inicial de Vôo (VIV)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_post_install_viv_defines_full_repair_lifecycle():
    viv = _read("docs/POS_INSTALACAO.md")
    for required in (
        "Verificação Inicial de Vôo (VIV)",
        "Inventariar ferramentas e capacidades",
        "Testar cada item de forma segura",
        "Pesquisar uma solução por falha",
        "Adicionar ou atualizar testes de regressão",
        "Não fazer merge enquanto checks estiverem pendentes/vermelhos",
        "INDISPONÍVEL NESTE RUNTIME",
        "BLOQUEADO POR AUTORIZAÇÃO",
        "Relatório obrigatório de saída",
    ):
        assert required.casefold() in viv.casefold(), required


def test_viv_is_linked_from_post_install_and_agent_startup_surfaces():
    expected_links = {
        "README.md": "docs/POS_INSTALACAO.md",
        "AGENTS.md": "docs/POS_INSTALACAO.md",
        "CLAUDE.md": "docs/POS_INSTALACAO.md",
        ".github/copilot-instructions.md": "docs/POS_INSTALACAO.md",
        "docs/INSTALACAO_WINDOWS.md": "POS_INSTALACAO.md",
        "docs/skills-connectors/CATALOG.md": "POS_INSTALACAO.md",
        "docs/skills-connectors/STARTUP_PROMPT.md": "docs/POS_INSTALACAO.md",
    }
    for path, required in expected_links.items():
        assert required in _read(path), path


def test_viv_requires_regression_tests_and_protects_production():
    viv = _read("docs/POS_INSTALACAO.md").casefold()
    assert "nunca desabilitar" in viv
    assert "produção" in viv
    assert "autorização explícita" in viv
    assert "rate limits" in viv
    assert "evidência" in viv
