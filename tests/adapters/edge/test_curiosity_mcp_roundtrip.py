"""End-to-end in-memory MCP tests for the curiosity intake tools."""

import json

import pytest

pytest.importorskip(
    "mcp",
    reason="The MCP SDK is installed by the Windows edge integration test workflow.",
)

from mcp.shared.memory import create_connected_server_and_client_session

from app.adapters.edge import jarvis_desktop_mcp
from app.application.services.curiosity_intake import CuriosityIntake


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _tool_payload(result):
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    text_blocks = [
        item.text for item in result.content if getattr(item, "text", None) is not None
    ]
    if not text_blocks:
        raise AssertionError("MCP tool returned no structured or textual payload")
    return json.loads(text_blocks[0])


@pytest.mark.anyio
async def test_curiosity_mcp_tools_round_trip_through_registered_intake(
    monkeypatch, tmp_path
):
    """The actual MCP client/server path must persist and retrieve one discovery."""
    intake = CuriosityIntake(storage_path=str(tmp_path / "inbox.jsonl"))
    resolved_components = []

    def resolve(component_id):
        resolved_components.append(component_id)
        if component_id != "curiosity_intake":
            raise AssertionError(f"unexpected Nexus component: {component_id}")
        return intake

    monkeypatch.setattr(jarvis_desktop_mcp.nexus, "resolve", resolve)

    async with create_connected_server_and_client_session(
        jarvis_desktop_mcp.mcp,
        raise_exceptions=True,
    ) as session:
        captured_result = await session.call_tool(
            "curiosity_capture",
            {
                "source_title": "Adaptive queue scheduling",
                "observation": "A documented scheduling approach may reduce queue wait time.",
                "source_type": "research",
                "source_uri": "https://example.test/adaptive-scheduling",
                "evidence_level": "documented",
                "user_benefit": "Could reduce waiting time for multi-agent tasks.",
                "jarvis_benefit": "Could improve task scheduling efficiency.",
                "connections": ["multi-agent queue"],
                "open_questions": ["Can the approach be reproduced with the current queue?"],
            },
        )
        listed_result = await session.call_tool(
            "curiosity_list_recent",
            {"limit": 5},
        )

    assert getattr(captured_result, "isError", False) is False
    assert getattr(listed_result, "isError", False) is False

    captured = _tool_payload(captured_result)
    listed = _tool_payload(listed_result)

    assert captured["success"] is True
    assert captured["duplicate"] is False
    assert captured["record"]["status"] == "captured"
    assert captured["record"]["evidence_level"] == "documented"

    assert listed["success"] is True
    assert listed["total"] == 1
    assert listed["records"][0]["id"] == captured["record"]["id"]
    assert resolved_components == ["curiosity_intake", "curiosity_intake"]
