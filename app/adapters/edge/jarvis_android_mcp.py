"""Loopback-only Streamable HTTP MCP server for the Android/Termux host.

The native APK owns Android UI automation. This Termux process only forwards
authenticated MCP requests to the APK's loopback AccessibilityService endpoint.
"""
from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

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
        "Android host diagnostics and opt-in native accessibility controls. "
        "Accessibility requires the device owner to enable Jarvis Accessibility "
        "in Android Settings and pair a local bearer token. Wi-Fi SSID, BSSID, "
        "IP addresses, location, clipboard contents, and credentials are never "
        "returned by host diagnostic tools. The MCP server binds to loopback."
    ),
)

_ACCESSIBILITY_URL = os.environ.get(
    "JARVIS_ANDROID_ACCESSIBILITY_URL", "http://127.0.0.1:18766"
).rstrip("/")
_ACCESSIBILITY_TOKEN_FILE = Path.home() / ".config/jarvis/accessibility/token"
_ACCESSIBILITY_TIMEOUT = 10
_ACCESSIBILITY_MAX_RESPONSE = 2 * 1024 * 1024


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


def _accessibility_token() -> str:
    token = os.environ.get("JARVIS_ANDROID_ACCESSIBILITY_TOKEN", "").strip()
    if not token:
        try:
            token = _ACCESSIBILITY_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    if len(token) < 40 or len(token) > 256:
        raise RuntimeError("Android accessibility pairing token is missing or invalid.")
    return token


def _accessibility_endpoint() -> str:
    parsed = urllib.parse.urlsplit(_ACCESSIBILITY_URL)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port not in {None, 18766}
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Android accessibility endpoint must use HTTP loopback on port 18766.")
    return _ACCESSIBILITY_URL


def _validate_accessibility_action(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Action payload must be an object.")
    action = payload.get("action")
    schemas = {
        "back": set(),
        "home": set(),
        "recents": set(),
        "tap": {"x", "y"},
        "swipe": {"x1", "y1", "x2", "y2", "duration_ms"},
        "click_text": {"text"},
        "click_view_id": {"view_id"},
        "set_text": {"view_id", "text"},
    }
    if action not in schemas:
        raise ValueError("Unsupported Android accessibility action.")
    allowed = {"action"} | schemas[action]
    if set(payload) - allowed:
        raise ValueError("Unexpected fields in Android accessibility action.")
    if action == "tap":
        _coordinates(payload, ("x", "y"))
    elif action == "swipe":
        _coordinates(payload, ("x1", "y1", "x2", "y2"))
        duration = payload.get("duration_ms", 350)
        if isinstance(duration, bool) or not isinstance(duration, int) or not 80 <= duration <= 1500:
            raise ValueError("duration_ms must be an integer between 80 and 1500.")
    elif action in {"click_text", "click_view_id"}:
        field = "text" if action == "click_text" else "view_id"
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise ValueError(f"{field} must be a non-empty string of at most 500 characters.")
    elif action == "set_text":
        view_id, value = payload.get("view_id"), payload.get("text")
        if not isinstance(view_id, str) or not view_id.strip() or len(view_id) > 300:
            raise ValueError("view_id must be a non-empty string of at most 300 characters.")
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError("text must be a string of at most 2000 characters.")
    return dict(payload)


def _coordinates(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10000:
            raise ValueError(f"{field} must be a number between 0 and 10000.")


def _accessibility_request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    endpoint = _accessibility_endpoint()
    token = _accessibility_token()
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint + path,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_ACCESSIBILITY_TIMEOUT) as response:
            raw = response.read(_ACCESSIBILITY_MAX_RESPONSE + 1)
        if len(raw) > _ACCESSIBILITY_MAX_RESPONSE:
            raise RuntimeError("Android accessibility response exceeded the configured size limit.")
        result = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise RuntimeError("Android accessibility bridge rejected the pairing token.") from None
        if error.code == 404:
            raise RuntimeError("Android AccessibilityService is not running or the endpoint is unavailable.") from None
        raise RuntimeError(f"Android accessibility bridge returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Cannot reach Android AccessibilityService at the configured loopback endpoint.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Android accessibility bridge returned an invalid response.") from None
    if not isinstance(result, dict):
        raise RuntimeError("Android accessibility bridge returned an invalid response shape.")
    return result


@mcp.tool()
def android_accessibility_status() -> dict:
    """Check whether the native Android accessibility service and local bridge are reachable."""
    return _accessibility_request("/healthz")


@mcp.tool()
def android_accessibility_snapshot() -> dict:
    """Read a bounded snapshot of the active Android window's accessibility tree."""
    return _accessibility_request("/v1/snapshot")


@mcp.tool()
def android_accessibility_screenshot() -> dict:
    """Capture the Android display (Android 11+); image is returned as base64 JPEG."""
    return _accessibility_request("/v1/screenshot")


@mcp.tool()
def android_accessibility_action(action: str, parameters: dict[str, Any] | None = None) -> dict:
    """Execute one allowlisted tap, swipe, semantic click, text entry, or global navigation action."""
    payload = _validate_accessibility_action({"action": action, **(parameters or {})})
    return _accessibility_request("/v1/action", payload)


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
