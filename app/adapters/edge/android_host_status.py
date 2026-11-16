"""Bounded, read-only diagnostics for the local Android/Termux host.

No shell is invoked. Termux:API commands are called by absolute executable
resolution and their output is reduced to an explicit allowlist before it can
cross the MCP boundary.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

_TERMUX_API_TIMEOUT_SECONDS = 5
_BATTERY_FIELDS = {
    "health",
    "percentage",
    "plugged",
    "present",
    "status",
    "technology",
    "temperature",
    "voltage",
    "current",
    "current_average",
}
_WIFI_FIELDS = {
    "wifi_enabled",
    "supplicant_state",
    "frequency_mhz",
    "link_speed_mbps",
    "rssi",
}


def _termux_api_json(command: str, allowed_fields: set[str]) -> dict[str, Any]:
    executable = shutil.which(command)
    if executable is None:
        return {"available": False, "status": "termux_api_not_installed"}

    try:
        result = subprocess.run(
            [executable],
            capture_output=True,
            text=True,
            timeout=_TERMUX_API_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"available": False, "status": "timeout"}
    except OSError:
        return {"available": False, "status": "execution_error"}

    if result.returncode != 0:
        return {"available": False, "status": "command_failed"}

    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return {"available": False, "status": "invalid_response"}

    if not isinstance(payload, dict):
        return {"available": False, "status": "invalid_response"}

    # Never forward SSID, BSSID, IP addresses, or arbitrary API output.
    filtered = {
        ("battery_status" if key == "status" and command == "termux-battery-status" else key): value
        for key, value in payload.items()
        if key in allowed_fields
        and isinstance(value, (str, int, float, bool, type(None)))
    }
    if command == "termux-wifi-connectioninfo":
        state = str(filtered.get("supplicant_state", "")).upper()
        filtered["connected"] = state == "COMPLETED" and filtered.get("wifi_enabled") is not False
    return {"available": True, "status": "ok", **filtered}


def android_device_status() -> dict[str, Any]:
    """Return non-identifying runtime and storage diagnostics for this host."""
    uptime_seconds: float | None = None
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError):
        pass

    storage: dict[str, dict[str, int]] = {}
    for label, path in (("home", Path.home()), ("termux_prefix", Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")))):
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        storage[label] = {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}

    return {
        "status": "ok",
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "termux_environment": bool(os.environ.get("PREFIX", "").endswith("/com.termux/files/usr")),
        "termux_api_cli_available": shutil.which("termux-battery-status") is not None,
        "uptime_seconds": uptime_seconds,
        "storage": storage,
    }


def android_battery_status() -> dict[str, Any]:
    """Return an allowlisted battery snapshot from Termux:API, if available."""
    return _termux_api_json("termux-battery-status", _BATTERY_FIELDS)


def android_wifi_status() -> dict[str, Any]:
    """Return Wi-Fi link state without disclosing SSID, BSSID, or IP addresses."""
    return _termux_api_json("termux-wifi-connectioninfo", _WIFI_FIELDS)
