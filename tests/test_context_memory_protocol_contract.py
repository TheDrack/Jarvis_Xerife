"""Contract tests for the provider-neutral Jarvis context/memory bootstrap."""
from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_protocol_defines_bootstrap_consolidation_and_provider_limits():
    protocol = _read("docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md")
    for required in (
        "Bootstrap",
        "Consolidate",
        "Deduplicate",
        "Conflict handling",
        "NOT PERSISTED",
        "provider-native memory",
        "Never report `persisted: true` without a successful backend confirmation",
    ):
        assert required.casefold() in protocol.casefold()


def test_all_repository_startup_surfaces_reference_the_protocol():
    surfaces = (
        "AGENTS.md",
        "CLAUDE.md",
        ".github/copilot-instructions.md",
        "docs/skills-connectors/STARTUP_PROMPT.md",
        "docs/skills-connectors/CATALOG.md",
        "app/adapters/edge/jarvis_desktop_mcp.py",
    )
    for relative_path in surfaces:
        assert "CONTEXT_MEMORY_PROTOCOL.md" in _read(relative_path), relative_path


def test_catalog_links_to_the_portable_skill_and_protocol():
    catalog = _read("docs/skills-connectors/CATALOG.md")
    skill_path = ROOT / "skills/jarvis-context-memory/SKILL.md"
    protocol_path = ROOT / "docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md"
    assert skill_path.is_file()
    assert protocol_path.is_file()
    assert "skills/jarvis-context-memory/SKILL.md" in catalog
    assert "CONTEXT_MEMORY_PROTOCOL.md" in catalog


def test_status_envelope_defaults_to_not_persisted():
    protocol = _read("docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md")
    match = re.search(r"```json\s*(.*?)\s*```", protocol, re.DOTALL)
    assert match, "protocol must publish a machine-readable status envelope"
    envelope = json.loads(match.group(1))
    assert envelope["protocol"] == "JCMP/1.0"
    assert envelope["memory_update"]["persisted"] is False
