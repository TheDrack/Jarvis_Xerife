"""Contract tests for the portable Jarvis VIV skill."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_viv_skill_has_required_frontmatter_and_canonical_references():
    skill = (ROOT / "skills/jarvis-viv/SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\n")
    assert "name: jarvis-viv" in skill
    assert "description:" in skill
    assert "docs/POS_INSTALACAO.md" in skill
    assert "docs/skills-connectors/CATALOG.md" in skill
    assert "docs/skills-connectors/CAPABILITY_INVENTORY.md" in skill


def test_viv_skill_requires_live_connector_discovery_research_and_resolution():
    skill = (ROOT / "skills/jarvis-viv/SKILL.md").read_text(encoding="utf-8").casefold()
    for phrase in (
        "re-read and select skills",
        "discover and list live connectors/tools",
        "research before guessing",
        "apply fixes through controlled engineering",
        "never remove, skip, weaken, or disable valid tests",
        "bloqueado por autorização",
        "não testado",
    ):
        assert phrase in skill

def test_catalog_viv_skill_is_a_separate_markdown_table_row():
    catalog = (ROOT / "docs/skills-connectors/CATALOG.md").read_text(encoding="utf-8")
    rows = catalog.splitlines()

    assert r"\n| VIV — Verificação Inicial de Voo |" not in catalog
    assert any(row.startswith("| Visual navigation |") for row in rows)
    assert any(row.startswith("| VIV — Verificação Inicial de Voo |") for row in rows)

