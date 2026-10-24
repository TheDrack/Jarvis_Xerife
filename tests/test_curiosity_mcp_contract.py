import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# Read the committed baseline from Git, not the mutable working file: legacy tests and
# self-healing hooks may rewrite data/context.json during the test session.
_CONTEXT_SNAPSHOT = json.loads(subprocess.run(
    ["git", "show", "HEAD:data/context.json"],
    cwd=ROOT,
    check=True,
    capture_output=True,
    text=True,
    encoding="utf-8",
).stdout)


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
