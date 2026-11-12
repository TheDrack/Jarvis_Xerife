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

def enable_windows_per_monitor_dpi_awareness() -> bool:
    """Request per-monitor-v2 DPI awareness before GUI libraries initialize.

    Returns False off Windows or when Windows refuses the process-level change
    (for example, because an application manifest already fixed the awareness).
    Callers must still compare screenshot and input dimensions before clicking.
    """
    import os

    if os.name != "nt":
        return False

    import ctypes

    user32 = ctypes.windll.user32
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return True
    except (AttributeError, OSError):
        pass

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE == 2
        shcore = ctypes.windll.shcore
        result = shcore.SetProcessDpiAwareness(2)
        if result == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        return bool(user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def screen_coordinate_spaces_compatible(
    screenshot_size: tuple[int, int],
    input_size: tuple[int, int],
    *,
    aspect_tolerance: float = 0.005,
) -> bool:
    """Check that screenshot and pointer APIs describe the same full-screen view.

    Pixel dimensions may differ because the screenshot is resized or Windows
    exposes logical input pixels. Equal aspect ratio (within rounding tolerance)
    is the invariant needed to map normalized full-screen points between them.
    Cropped screenshots must not be passed to this API.
    """
    try:
        screenshot_width, screenshot_height = screenshot_size
        input_width, input_height = input_size
        values = (
            screenshot_width, screenshot_height, input_width, input_height,
            aspect_tolerance,
        )
        if any(isinstance(value, bool) for value in values):
            return False
        if any(not math.isfinite(float(value)) for value in values):
            return False
        if any(int(value) != value for value in values[:4]):
            return False
        if min(screenshot_width, screenshot_height, input_width, input_height) <= 0:
            return False
        if aspect_tolerance < 0:
            return False
        screenshot_ratio = screenshot_width / screenshot_height
        input_ratio = input_width / input_height
        return abs(screenshot_ratio - input_ratio) <= aspect_tolerance
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False
