"""Loopback-only Streamable HTTP MCP server for the Android/Termux host.

The native APK owns Android UI automation. This Termux process only forwards
authenticated MCP requests to the APK's loopback AccessibilityService endpoint.
"""
from __future__ import annotations

import contextlib
import os
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.adapters.edge.android_accessibility_client import (
    accessibility_request,
    validate_accessibility_action,
)
from app.adapters.edge.android_host_status import (
    android_battery_status as read_battery_status,
    android_device_status as read_device_status,
    android_wifi_status as read_wifi_status,
)

mcp = FastMCP(
    "Jarvis Android",
    instructions=(
        "Android host diagnostics and opt-in native accessibility controls. "
        "Accessibility requires the device owner to enable Jarvis Accessibility "
        "in Android Settings and pair a local bearer token. Wi-Fi SSID, BSSID, "
        "IP addresses, location, clipboard contents, and credentials are never "
        "returned by host diagnostic tools. The MCP server binds to loopback."
    ),
)


@mcp.tool()
def android_device_status() -> dict:
    """Inspect Android/Termux runtime, uptime, and aggregate storage usage."""
    return read_device_status()


@mcp.tool()
def android_battery_status() -> dict:
    """Read battery state through Termux:API without changing device state."""
    return read_battery_status()


@mcp.tool()
def android_wifi_status() -> dict:
    """Read Wi-Fi link state while withholding SSID, BSSID, and IP addresses."""
    return read_wifi_status()


@mcp.tool()
def android_accessibility_status() -> dict:
    """Check whether the native Android accessibility service and local bridge are reachable."""
    return accessibility_request("/healthz")


@mcp.tool()
def android_accessibility_snapshot() -> dict:
    """Read a bounded snapshot of the active Android window's accessibility tree."""
    return accessibility_request("/v1/snapshot")


@mcp.tool()
def android_accessibility_screenshot() -> dict:
    """Capture the Android display (Android 11+); image is returned as base64 JPEG."""
    return accessibility_request("/v1/screenshot")


@mcp.tool()
def android_accessibility_action(action: str, parameters: dict[str, Any] | None = None) -> dict:
    """Execute one allowlisted tap, swipe, semantic click, text entry, or global navigation action."""
    payload = validate_accessibility_action({"action": action, **(parameters or {})})
    return accessibility_request("/v1/action", payload)


async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "live", "service": "jarvis-android-mcp"})


async def readyz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ready", "service": "jarvis-android-mcp"})


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/readyz", readyz, methods=["GET"]),
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan,
)


def main() -> None:
    host = os.environ.get("JARVIS_ANDROID_MCP_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Jarvis Android MCP must bind to loopback only.")
    try:
        port = int(os.environ.get("JARVIS_ANDROID_MCP_PORT", "8765"))
    except ValueError as exc:
        raise RuntimeError("JARVIS_ANDROID_MCP_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("JARVIS_ANDROID_MCP_PORT must be between 1 and 65535.")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
