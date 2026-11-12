import pytest

from app.adapters.edge.screen_coordinates import normalized_to_screen_point


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
