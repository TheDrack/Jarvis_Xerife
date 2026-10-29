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
