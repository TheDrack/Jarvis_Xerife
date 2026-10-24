# -*- coding: utf-8 -*-
"""Ferramentas MCP `mobile_*` para Android. Grupo registrado no servidor desktop existente.

O módulo não importa dependências de desktop (pyautogui/opencv), então pode ser testado
isoladamente. O servidor MCP chama `register_mobile_tools(mcp, navigator)`.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.server.fastmcp import Image
from mcp.types import TextContent

from app.adapters.connection.adb_connection import ALLOWED_KEYCODES

MOBILE_CAPABILITIES = (
    "mobile.observe",
    "mobile.tap",
    "mobile.type",
    "mobile.key",
    "mobile.launch_app",
)


def _blocks(result: dict[str, Any]) -> list[Any]:
    """Texto com metadados e, se houver captura, a imagem real como bloco MCP."""
    metadata = {k: v for k, v in result.items() if k != "screenshot_png_b64"}
    blocks: list[Any] = [TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False, default=str))]
    encoded = result.get("screenshot_png_b64")
    if encoded:
        blocks.append(Image(data=base64.b64decode(encoded), format="png"))
    return blocks


def register_mobile_tools(mcp: Any, navigator: Any) -> None:
    """Registra as ferramentas `mobile_*` no servidor MCP informado."""

    @mcp.tool(structured_output=False)
    def mobile_observe(device_id: str) -> list[Any]:
        """Capture the Android screen (PNG) and list visible UI elements with resource ids and text."""
        return _blocks(navigator.observe(device_id))

    @mcp.tool()
    def mobile_find_element(device_id: str, resource_id: str = "", text: str = "") -> dict[str, Any]:
        """Check whether exactly one element matches resource_id or text. Never taps."""
        return navigator.find(device_id, resource_id or None, text or None)

    @mcp.tool(structured_output=False)
    def mobile_run_recipe(device_id: str, steps: list[dict[str, Any]], user_confirmed: bool = False) -> list[Any]:
        """Run up to 20 steps (tap/type/key/launch/stop/swipe), each verified by a postcondition.

        Steps that send, pay, delete or publish require user_confirmed=true, checked before any step runs.
        """
        result = navigator.run_recipe(device_id, steps, user_confirmed=user_confirmed)
        return _blocks(_with_screen(navigator, device_id, result))

    @mcp.tool(structured_output=False)
    def mobile_tap(device_id: str, resource_id: str = "", text: str = "", user_confirmed: bool = False) -> list[Any]:
        """Tap one uniquely identified element. Ambiguous or missing targets are not tapped."""
        step = {"action": "tap", "target": {"resource_id": resource_id or None, "text": text or None}}
        result = navigator.run_recipe(device_id, [step], user_confirmed=user_confirmed)
        return _blocks(_with_screen(navigator, device_id, result))

    @mcp.tool(structured_output=False)
    def mobile_type(device_id: str, text: str, user_confirmed: bool = False) -> list[Any]:
        """Type ASCII text into the focused field. Sensitive text requires user_confirmed=true."""
        step = {"action": "type", "value": text}
        result = navigator.run_recipe(device_id, [step], user_confirmed=user_confirmed)
        return _blocks(_with_screen(navigator, device_id, result))

    @mcp.tool(structured_output=False)
    def mobile_press_key(device_id: str, keycode: int) -> list[Any]:
        """Press one allowed key: 3 HOME, 4 BACK, 24/25 volume, 66 ENTER, 67 DEL, 187 APP_SWITCH, 223 SLEEP, 224 WAKEUP."""
        if keycode not in ALLOWED_KEYCODES:
            return _blocks({"status": "invalid_recipe", "message": f"keycode {keycode} não permitido"})
        result = navigator.run_recipe(device_id, [{"action": "key", "value": keycode}])
        return _blocks(_with_screen(navigator, device_id, result))

    @mcp.tool(structured_output=False)
    def mobile_launch_app(device_id: str, package: str) -> list[Any]:
        """Launch an installed Android app by package name (e.g. com.android.settings)."""
        result = navigator.run_recipe(device_id, [{"action": "launch", "value": package}])
        return _blocks(_with_screen(navigator, device_id, result))


def _with_screen(navigator: Any, device_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Anexa captura nova após ações concluídas ou falhas que deixam a tela em estado incerto."""
    if result.get("status") in ("completed", "postcondition_failed", "not_found", "ambiguous"):
        observed = navigator.observe(device_id)
        if observed.get("status") == "observed":
            return {**result, "screenshot_png_b64": observed["screenshot_png_b64"]}
    return result
