import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Capture the checked-in snapshot during collection, before legacy tests mutate this file.
_CONTEXT_SNAPSHOT = json.loads((ROOT / "data/context.json").read_text(encoding="utf-8"))


def test_curiosity_intake_is_registered_and_exposed_through_mcp():
    registry = json.loads((ROOT / "data/nexus_registry.json").read_text(encoding="utf-8"))
    assert registry["components"]["curiosity_intake"] == (
        "app.application.services.curiosity_intake.CuriosityIntake"
    )

    mcp_source = (ROOT / "app/adapters/edge/jarvis_desktop_mcp.py").read_text(encoding="utf-8")
    assert "def curiosity_capture(" in mcp_source
    assert "def curiosity_list_recent(" in mcp_source
    assert "def reconnection_briefing(" in mcp_source
    assert "curiosity_capture" in mcp_source
    assert "curiosity_list_recent" in mcp_source
    assert "reconnection_briefing" in mcp_source
    assert registry["components"]["reconnection_briefing"] == (
        "app.application.services.reconnection_briefing.ReconnectionBriefing"
    )


def test_repository_default_context_is_paused_and_health_is_unknown():
    assert _CONTEXT_SNAPSHOT["evolution_state"] == "paused"
    assert _CONTEXT_SNAPSHOT["system_health"]["status"] == "unknown"
    assert _CONTEXT_SNAPSHOT["system_health"]["cpu_percent"] is None
    assert _CONTEXT_SNAPSHOT["system_health"]["ram_percent"] is None
