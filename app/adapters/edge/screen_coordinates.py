"""Coordinate transforms for visual desktop automation.

Use normalized points from the image as the stable interchange format: they
remain valid when a client scales the screenshot for display.
"""
from __future__ import annotations

import math


def normalized_to_screen_point(
    x_ratio: float,
    y_ratio: float,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """Map a normalized screenshot point (0..1) to a pixel in the live screen.

    Ratios are relative to the complete screenshot, not a cropped sub-image.
    The right/bottom edges map to the final valid pixel.
    """
    x_ratio = float(x_ratio)
    y_ratio = float(y_ratio)
    if not math.isfinite(x_ratio) or not math.isfinite(y_ratio):
        raise ValueError("Coordinate ratios must be finite numbers.")
    if not 0.0 <= x_ratio <= 1.0 or not 0.0 <= y_ratio <= 1.0:
        raise ValueError("Coordinate ratios must be between 0 and 1.")
    if isinstance(screen_width, bool) or isinstance(screen_height, bool):
        raise ValueError("Screen dimensions must be positive integers.")
    if int(screen_width) != screen_width or int(screen_height) != screen_height:
        raise ValueError("Screen dimensions must be positive integers.")
    screen_width, screen_height = int(screen_width), int(screen_height)
    if screen_width <= 0 or screen_height <= 0:
        raise ValueError("Screen dimensions must be positive integers.")

    return (
        round(x_ratio * (screen_width - 1)),
        round(y_ratio * (screen_height - 1)),
    )
