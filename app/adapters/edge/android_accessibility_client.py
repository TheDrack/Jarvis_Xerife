"""Authenticated, loopback-only client for the native Android accessibility bridge.

Kept independent from the MCP SDK so its validation and transport contract can
be tested in the repository's standard Python test environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ACCESSIBILITY_URL = os.environ.get(
    "JARVIS_ANDROID_ACCESSIBILITY_URL", "http://127.0.0.1:18766"
).rstrip("/")
ACCESSIBILITY_TOKEN_FILE = Path.home() / ".config/jarvis/accessibility/token"
ACCESSIBILITY_TIMEOUT = 10
ACCESSIBILITY_MAX_RESPONSE = 2 * 1024 * 1024
ANDROID_LLM_APPS = {
    "chatgpt": "com.openai.chatgpt",
    "claude": "com.anthropic.claude",
    "gemini": "com.google.android.googlequicksearchbox",
    "grok": "ai.x.grok",
    "qwen": "ai.qwenlm.chat.android",
}
ANDROID_LLM_APP_PACKAGES = frozenset(ANDROID_LLM_APPS.values())


def accessibility_token() -> str:
    token = os.environ.get("JARVIS_ANDROID_ACCESSIBILITY_TOKEN", "").strip()
    if not token:
        try:
            token = ACCESSIBILITY_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    if len(token) < 40 or len(token) > 256:
        raise RuntimeError("Android accessibility pairing token is missing or invalid.")
    return token


def accessibility_endpoint() -> str:
    parsed = urllib.parse.urlsplit(ACCESSIBILITY_URL)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 18766
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Android accessibility endpoint must use HTTP loopback on port 18766.")
    return ACCESSIBILITY_URL


def validate_accessibility_action(payload: dict[str, Any]) -> dict[str, Any]:
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
        "click_index": {"index"},
        "set_text_index": {"index", "text"},
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
    elif action in {"click_index", "set_text_index"}:
        index = payload.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < 300:
            raise ValueError("index must be an integer between 0 and 299.")
        if action == "set_text_index":
            value = payload.get("text")
            if not isinstance(value, str) or len(value) > 12000:
                raise ValueError("text must be a string of at most 12000 characters.")
    elif action == "set_text":
        view_id, value = payload.get("view_id"), payload.get("text")
        if not isinstance(view_id, str) or not view_id.strip() or len(view_id) > 300:
            raise ValueError("view_id must be a non-empty string of at most 300 characters.")
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError("text must be a string of at most 2000 characters.")
    return dict(payload)


def build_accessibility_action(action: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError("Action parameters must be an object.")
    if parameters and "action" in parameters:
        raise ValueError("Action parameters cannot override the selected action.")
    return validate_accessibility_action({"action": action, **(parameters or {})})


def build_accessibility_app_launch(app_id: str) -> dict[str, str]:
    if not isinstance(app_id, str) or app_id.strip().lower() not in ANDROID_LLM_APPS:
        raise ValueError("Android LLM app is not in the installed-app allowlist.")
    return {"package_name": ANDROID_LLM_APPS[app_id.strip().lower()]}


def _coordinates(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10000:
            raise ValueError(f"{field} must be a number between 0 and 10000.")


def accessibility_request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.startswith("/v1/") and path != "/healthz":
        raise ValueError("Invalid Android accessibility route.")
    endpoint = accessibility_endpoint()
    token = accessibility_token()
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
        with urllib.request.urlopen(request, timeout=ACCESSIBILITY_TIMEOUT) as response:
            raw = response.read(ACCESSIBILITY_MAX_RESPONSE + 1)
        if len(raw) > ACCESSIBILITY_MAX_RESPONSE:
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
