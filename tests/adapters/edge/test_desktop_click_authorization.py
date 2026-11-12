"""Security regression tests for desktop coordinate MCP tools."""

import json

import pytest

pytest.importorskip(
    "mcp",
    reason="The desktop MCP SDK is installed by the edge/Portas test workflow.",
)

from app.adapters.edge import jarvis_desktop_mcp as desktop_mcp


@pytest.mark.parametrize("tool_name,arguments", [
    (
        "click_at",
        {
            "x": 50,
            "y": 40,
            "target_description": "test target",
        },
    ),
    (
        "click_at_normalized",
        {
            "x_ratio": 0.5,
            "y_ratio": 0.5,
            "target_description": "test target",
        },
    ),
])
@pytest.mark.parametrize("user_confirmed", [False, True])
def test_coordinate_click_tools_fail_closed_without_host_approval(
    monkeypatch, tool_name, arguments, user_confirmed
):
    calls = []
    monkeypatch.setattr(
        desktop_mcp.navigator, "_capture",
        lambda: calls.append("capture"),
    )
    monkeypatch.setattr(
        desktop_mcp.navigator, "_gui",
        lambda: calls.append("gui"),
    )
    monkeypatch.setattr(
        desktop_mcp, "_show_agent_target",
        lambda *args: calls.append("target"),
    )

    registered = getattr(desktop_mcp, tool_name)
    handler = getattr(registered, "__wrapped__", registered)
    result = handler(**arguments, user_confirmed=user_confirmed)
    payload = json.loads(result[0].text)

    assert payload["success"] is False
    assert payload["status"] == "host_approval_unavailable"
    assert "host" in payload["message"].casefold()
    assert calls == []
