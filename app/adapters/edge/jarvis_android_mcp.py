"""Loopback-only Streamable HTTP MCP server for the Android/Termux host.

Run from the repository root with:
    python -m app.adapters.edge.jarvis_android_mcp

This server intentionally exposes only bounded, read-only device diagnostics.
It is separate from the desktop MCP entrypoint and does not import desktop UI,
ADB, Windows, or host-shell adapters.
"""
from __future__ import annotations

import contextlib
import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.adapters.edge.android_host_status import (
    android_battery_status as read_battery_status,
    android_device_status as read_device_status,
    android_wifi_status as read_wifi_status,
)

mcp = FastMCP(
    "Jarvis Android",
    instructions=(
        "Read-only diagnostics for the Android device hosting this MCP server. "
        "These tools report bounded host, battery, and Wi-Fi status. Wi-Fi SSID, "
        "BSSID, IP addresses, location, clipboard contents, and credentials are "
        "never returned. This server is intended to be reachable only through "
        "the local loopback interface and its configured Secure MCP Tunnel."
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


async def healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "live", "service": "jarvis-android-mcp"})


async def readyz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ready", "service": "jarvis-android-mcp"})


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    async with mcp.session_manager.run():
        yield


# FastMCP's default Streamable HTTP path is /mcp. Keep health routes ahead of
# Mount("/") because that mount otherwise captures every remaining path.
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
