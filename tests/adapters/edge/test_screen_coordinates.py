import json

import pytest

from app.adapters.edge import jarvis_desktop_mcp as desktop_mcp
from app.adapters.edge.screen_coordinates import normalized_to_screen_point, screen_coordinate_spaces_compatible


@pytest.mark.parametrize(
    ("x_ratio", "y_ratio", "screen_size", "expected"),
    [
        (0.0, 0.0, (1920, 1080), (0, 0)),
        (0.5, 0.5, (1920, 1080), (960, 540)),
        (1.0, 1.0, (1920, 1080), (1919, 1079)),
        # The same visual target maps correctly regardless of the displayed image size.
        (0.5, 0.5, (1648, 928), (824, 464)),
        (0.25, 0.75, (2560, 1440), (640, 1079)),
    ],
)
def test_normalized_point_maps_to_current_screen_pixels(
    x_ratio, y_ratio, screen_size, expected
):
    assert normalized_to_screen_point(x_ratio, y_ratio, *screen_size) == expected


@pytest.mark.parametrize(
    ("x_ratio", "y_ratio", "screen_size"),
    [
        (-0.01, 0.5, (1920, 1080)),
        (1.01, 0.5, (1920, 1080)),
        (0.5, -0.01, (1920, 1080)),
        (0.5, 1.01, (1920, 1080)),
        (float("nan"), 0.5, (1920, 1080)),
        (0.5, float("inf"), (1920, 1080)),
        (0.5, 0.5, (0, 1080)),
        (0.5, 0.5, (1920, -1)),
    ],
)
def test_normalized_point_rejects_invalid_ratios_and_dimensions(
    x_ratio, y_ratio, screen_size
):
    with pytest.raises(ValueError):
        normalized_to_screen_point(x_ratio, y_ratio, *screen_size)


@pytest.mark.parametrize(
    ("screenshot_size", "input_size", "expected"),
    [
        ((1920, 1080), (1920, 1080), True),
        # DPI scaling / client-side image resizing changes pixel dimensions, not the view.
        ((1648, 928), (1920, 1080), True),
        ((1920, 1080), (1536, 864), True),
        # Different aspect ratios may indicate a crop or a different display region.
        ((1920, 1080), (1280, 1024), False),
        ((0, 1080), (0, 1080), False),
        ((1920, 1080), (1920, 0), False),
    ],
)
def test_coordinate_spaces_must_describe_same_full_screen_view(
    screenshot_size, input_size, expected
):
    assert screen_coordinate_spaces_compatible(screenshot_size, input_size) is expected



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
