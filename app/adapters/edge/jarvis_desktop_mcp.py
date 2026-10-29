# -*- coding: utf-8 -*-
"""Local MCP server exposing the interactive Windows desktop to an MCP host.

Run from the repository root with:
    python -m app.adapters.edge.jarvis_desktop_mcp

The server uses stdio so screenshots and input events stay on this machine.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import TextContent

from app.adapters.edge.visual_navigation_adapter import VisualNavigationAdapter
from app.adapters.edge.background_window_input import click_window_background
from app.adapters.edge.jarvis_agent_status import set_agent_cursor_target, tracked_action
from app.core.nexus import nexus

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)


def _show_agent_target(x: int, y: int) -> None:
    """Mostra o cursor fantasma no ponto de clique (somente visual; nÃƒÂ£o move o mouse)."""
    try:
        set_agent_cursor_target(int(x), int(y), "target")
    except Exception as exc:
        logger.debug("Indicador visual indisponÃƒÂ­vel: %s", exc)

_HTTP_TRANSPORT = os.environ.get("JARVIS_DESKTOP_TRANSPORT", "stdio").strip().lower()
_HTTP_PORT = int(os.environ.get("JARVIS_DESKTOP_HTTP_PORT", "8765"))

mcp = FastMCP(
    "Jarvis Desktop",
    host="127.0.0.1",
    port=_HTTP_PORT,
    instructions=(
        "Jarvis exposes desktop tools and explicit Android navigation tools on this MCP server. "
        "The target is determined by the selected tool: desktop tools remain desktop-only; "
        "android_* tools target the explicitly configured authorized Android device. Never "
        "silently redirect one target to the other. The user chooses the connection software "
        "and transport; Tailscale, Aperture, and RDC are examples, not requirements. MCP is "
        "the tool interface, not a mandated network route. At session/task start, discover live "
        "tools and read AGENTS.md, docs/skills-connectors/CATALOG.md, and "
        "docs/skills-connectors/CONTEXT_MEMORY_PROTOCOL.md when repository files are available. "
        "Load relevant persisted Jarvis memory and task state, reconcile against live evidence, "
        "and mark stale/conflicting claims. At meaningful milestones and handoff, consolidate "
        "useful memory and confirm persistence; if no writable backend exists, mark the update "
        "NOT PERSISTED. Never claim provider-native memory changed without confirmation and never "
        "store secrets. When research, news, ideas, errors, or new tools reveal a possible improvement, "
        "use curiosity_capture and review curiosity_list_recent; captured ideas are not authorization to mutate. "
        "When reconnecting after an absence, use reconnection_briefing for recent discoveries, verified changes, "
        "pull requests, and test status. Check live sources before supplying PR/workflow states and distinguish "
        "ideas from implemented/tested work. Always observe before acting, prefer accessibility elements or image "
        "templates over raw coordinates, perform one action at a time, and verify the post-action "
        "state. Preserve existing behavior, test changes, and never claim success without evidence."
    ),
)
if _HTTP_TRANSPORT == "streamable-http":
    # Tailscale Serve is the only remote ingress; keep the MCP app loopback-only.
    # The reverse proxy supplies the tailnet hostname, so derive a narrow host
    # allowlist from the authenticated local Tailscale status instead of disabling
    # DNS-rebinding protection.
    from mcp.server.transport_security import TransportSecuritySettings

    _allowed_hosts = [
        host.strip().lower()
        for host in os.environ.get("JARVIS_DESKTOP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    _allowed_origins = [
        origin.strip().lower()
        for origin in os.environ.get("JARVIS_DESKTOP_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if not _allowed_hosts:
        raise RuntimeError(
            "JARVIS_DESKTOP_ALLOWED_HOSTS precisa conter o DNS privado do Tailscale."
        )
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    )
navigator = VisualNavigationAdapter()


@mcp.tool()
def jarvis_agent_bootstrap() -> dict[str, Any]:
    """Return the canonical Jarvis startup contract and repo capability inventory.

    Call this at the start of a task before other Jarvis operations. This is a
    repository baseline, not a substitute for inspecting the calling host's
    live tool registry, permissions, or connected services.
    """
    documents = {
        "agent_contract": _REPO_ROOT / "AGENTS.md",
        "catalog": _REPO_ROOT / "docs" / "skills-connectors" / "CATALOG.md",
        "capability_inventory": _REPO_ROOT / "docs" / "skills-connectors" / "CAPABILITY_INVENTORY.md",
        "context_memory_protocol": _REPO_ROOT / "docs" / "skills-connectors" / "CONTEXT_MEMORY_PROTOCOL.md",
        "startup_prompt": _REPO_ROOT / "docs" / "skills-connectors" / "STARTUP_PROMPT.md",
    }
    loaded: dict[str, str] = {}
    unavailable: dict[str, str] = {}
    for name, path in documents.items():
        try:
            loaded[name] = path.read_text(encoding="utf-8")
        except OSError as exc:
            unavailable[name] = f"{type(exc).__name__}: {exc}"

    return {
        "protocol": "JCMP/1.0",
        "source": "repository_baseline",
        "documents_loaded": sorted(loaded),
        "documents_unavailable": unavailable,
        "documents": loaded,
        "runtime_registry": {
            "status": "not_visible_to_jarvis_server",
            "required_action": (
                "Inspect the calling host's live tool/MCP registry and schemas; "
                "reconcile it with this repository baseline."
            ),
        },
        "mandatory_preflight": [
            "Read host/project instructions and this catalog/protocol.",
            "Inspect live tools, schemas, authorization and connection state; never infer them from documentation.",
            "Load relevant persistent task/memory state and reconcile it against live evidence.",
            "Before an action, confirm prerequisites, allowed side effects, success evidence and rollback.",
            "After a tool failure or domain/connector change, refresh discovery and consult the relevant skill before retrying.",
            "At milestones/handoff, report evidence, blockers, next action and whether memory persistence was confirmed.",
        ],
        "claim_policy": {
            "allowed_statuses": [
                "IMPLEMENTED",
                "AVAILABLE_IN_RUNTIME",
                "AUTHORIZED",
                "TESTED",
                "PRODUCTION_VERIFIED",
                "FAILED",
                "UNAVAILABLE_IN_RUNTIME",
                "NOT_TESTED",
                "BLOCKED_BY_AUTHORIZATION",
            ],
            "rule": "Never claim a stronger status than the evidence proves.",
        },
    }


@mcp.tool()
def curiosity_capture(
    source_title: str,
    observation: str,
    source_type: str = "other",
    source_uri: str = "",
    evidence_level: str = "unverified",
    user_benefit: str = "",
    jarvis_benefit: str = "",
    connections: list[str] | None = None,
    open_questions: list[str] | None = None,
    experiment: str = "",
    risks: list[str] | None = None,
) -> dict[str, Any]:
    """Record a research/news/idea/error discovery as a deduplicated curiosity card.

    This records an observation only. It does not execute code, modify files, or
    enable auto-evolution. Provide source evidence and concrete user/Jarvis benefit
    where known; unsupported claims should remain unverified.
    """
    try:
        intake = nexus.resolve("curiosity_intake")
        if intake is None or not hasattr(intake, "execute"):
            return {"success": False, "error": "curiosity_intake unavailable"}
        return intake.execute({
            "action": "capture",
            "source_title": source_title,
            "observation": observation,
            "source_type": source_type,
            "source_uri": source_uri,
            "evidence_level": evidence_level,
            "user_benefit": user_benefit,
            "jarvis_benefit": jarvis_benefit,
            "connections": connections or [],
            "open_questions": open_questions or [],
            "experiment": experiment,
            "risks": risks or [],
        })
    except Exception as exc:
        logger.exception("Curiosity capture failed")
        return {"success": False, "error": str(exc)}


@mcp.tool()
def curiosity_list_recent(limit: int = 20) -> dict[str, Any]:
    """List recent curiosity cards so agents can deduplicate research and follow up."""
    try:
        intake = nexus.resolve("curiosity_intake")
        if intake is None or not hasattr(intake, "execute"):
            return {"success": False, "error": "curiosity_intake unavailable"}
        return intake.execute({"action": "list_recent", "limit": limit})
    except Exception as exc:
        logger.exception("Curiosity list failed")
        return {"success": False, "error": str(exc)}


@mcp.tool()
def reconnection_briefing(
    verified_updates: list[dict[str, Any]] | None = None,
    pull_requests: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Build a returning-user greeting from recent curiosity cards and live-verified updates.

    Before supplying pull_requests or verified_updates, check current repository/workflow
    state. Never label an idea as implemented or a PR as green without evidence.
    """
    try:
        briefing = nexus.resolve("reconnection_briefing")
        if briefing is None or not hasattr(briefing, "execute"):
            return {"success": False, "error": "reconnection_briefing unavailable"}
        return briefing.execute({
            "verified_updates": verified_updates or [],
            "pull_requests": pull_requests or [],
            "limit": limit,
        })
    except Exception as exc:
        logger.exception("Reconnection briefing failed")
        return {"success": False, "error": str(exc)}


def _content(result: dict[str, Any], *, include_frames: bool = True) -> list[Any]:
    """Return concise status text plus actual MCP image blocks for the model to inspect."""
    metadata = {
        key: value
        for key, value in result.items()
        if key not in {"screenshot_data_url", "frames", "image_base64"}
    }
    blocks: list[Any] = [
        TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False, default=str))
    ]
    screenshot_path = result.get("screenshot_path")
    if screenshot_path and Path(screenshot_path).is_file():
        blocks.append(Image(path=screenshot_path))
    if include_frames:
        for frame in result.get("frames", []):
            value = str(frame.get("image", ""))
            if value.startswith("data:image/") and "," in value:
                raw = base64.b64decode(value.split(",", 1)[1], validate=True)
                blocks.append(Image(data=raw, format="jpeg"))
    return blocks


def _observe_after_action(
    result: dict[str, Any], *, include_success_screenshot: bool = True
) -> dict[str, Any]:
    """Attach a screen when useful; verified batch actions avoid redundant image payloads."""
    if result.get("screenshot_path"):
        return result
    if result.get("success") and not include_success_screenshot:
        return result
    observation = navigator.observe_screen()
    return {**observation, **result}


@mcp.tool(structured_output=False)
@tracked_action("Observando tela")
def observe_screen() -> list[Any]:
    """Capture the current desktop; return status and the screen as an MCP image."""
    return _content(navigator.observe_screen())


@mcp.tool(structured_output=False)
@tracked_action("Observando mudanÃƒÂ§as na tela")
def watch_screen(duration_seconds: float = 3, fps: float = 1) -> list[Any]:
    """Return a short, finite sequence of recent screen images (up to 6 seconds, 2 FPS)."""
    return _content(navigator.watch_screen(duration_seconds, fps))


@mcp.tool(structured_output=False)
@tracked_action("Executando receita visual")
def run_visual_recipe(steps: list[dict[str, Any]]) -> list[Any]:
    """Click unique saved image templates, verifying a distinct postcondition after each click.

    If a target is missing or ambiguous, stop and return the current screenshot to the model.
    Keep recipes short; each step requires template_id and verify_template_id.
    """
    result = navigator.run_recipe(steps)
    # A completed recipe already verified each postcondition. Avoid sending a
    # redundant final screenshot; uncertain/failed recipes still include evidence.
    return _content(_observe_after_action(
        result, include_success_screenshot=result.get("status") != "completed"
    ))


@mcp.tool()
@tracked_action("Capturando template visual")
def capture_visual_template(
    template_id: str,
    user_confirmed: bool,
    display_name: str = "",
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    """Open Windows Snipping Tool and save the user's selected control as a reusable template.

    Ask the user first and call only after they explicitly agree. user_confirmed must be true.
    """
    if not user_confirmed:
        return {
            "success": False,
            "status": "confirmation_required",
            "message": "PeÃƒÂ§a autorizaÃƒÂ§ÃƒÂ£o explÃƒÂ­cita ao usuÃƒÂ¡rio antes de abrir o recorte.",
        }
    return navigator.capture_template_from_clipboard(template_id, display_name, timeout_seconds)


@mcp.tool()
@tracked_action("Listando templates visuais")
def list_visual_templates() -> dict[str, Any]:
    """List saved template identifiers and display names."""
    return {"templates": navigator._read_catalog()}


@mcp.tool(structured_output=False)
@tracked_action("Acionando controle acessÃƒÂ­vel")
def click_accessibility(
    target_name: str,
    window_title_contains: str = "",
    control_type: str = "",
    expected_name_after: str = "",
    timeout_seconds: float = 2.0,
) -> list[Any]:
    """Click a unique visible UI Automation control by exact accessible name.

    Optionally verify that expected_name_after becomes visible. Ambiguous targets are never clicked.
    """
    return _content(navigator.click_accessibility(
        target_name, window_title_contains, control_type, expected_name_after, timeout_seconds
    ))


@mcp.tool(structured_output=False)
@tracked_action("Preenchendo campo acessÃƒÂ­vel")
def set_accessibility_value(
    target_name: str,
    value: str,
    window_title_contains: str = "",
    control_type: str = "Edit",
    expected_value: str = "",
) -> list[Any]:
    """Set and verify a uniquely identified accessible text field without global keyboard input."""
    return _content(navigator.set_accessibility_value(
        target_name, value, window_title_contains, control_type, expected_value
    ))


@mcp.tool()
@tracked_action("Clique em segundo plano")
def click_window_background_at(
    window_title_contains: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    """Post a click to a unique visible Windows window without moving the user's cursor.

    x/y are screen coordinates from the current desktop screenshot. The API maps them
    to the target window's client area. Some apps ignore background messages; success
    only confirms messages were queued, so observe and verify the target state.
    """
    _show_agent_target(x, y)
    return click_window_background(window_title_contains, x, y, coordinates_are_screen=True)


@mcp.tool(structured_output=False)
@tracked_action("Clique fÃƒÂ­sico autorizado")
def click_at(
    x: int,
    y: int,
    target_description: str,
    user_confirmed: bool,
) -> list[Any]:
    """One-off coordinate fallback; use only after observing and with explicit user approval."""
    if not user_confirmed:
        return [{
            "success": False,
            "status": "confirmation_required",
            "message": "PeÃƒÂ§a autorizaÃƒÂ§ÃƒÂ£o explÃƒÂ­cita para o clique por coordenadas.",
        }]
    screenshot = navigator._capture()
    if x < 0 or y < 0 or x >= screenshot.width or y >= screenshot.height:
        return _content({
            "success": False,
            "status": "coordinates_out_of_bounds",
            "target_description": target_description,
            **navigator._save_observation(screenshot),
        })
    _show_agent_target(x, y)
    navigator._gui().click(x, y, button="left")
    return _content(_observe_after_action({
        "success": True,
        "status": "clicked",
        "target_description": target_description,
        "x": x,
        "y": y,
    }))


@mcp.tool(structured_output=False)
@tracked_action("Digitando texto")
def type_text(text: str) -> list[Any]:
    """Type user-provided text into the currently focused window and return a fresh screenshot."""
    if len(text) > 10000:
        return [{"success": False, "status": "input_too_long", "message": "Limite: 10.000 caracteres."}]
    navigator._gui().write(text, interval=0.01)
    return _content(_observe_after_action({"success": True, "status": "typed", "characters": len(text)}))


@mcp.tool(structured_output=False)
@tracked_action("Rolando a janela")
def scroll(amount: int) -> list[Any]:
    """Scroll the active window a small bounded amount and return a fresh screenshot."""
    if amount == 0 or abs(amount) > 20:
        return [{"success": False, "status": "invalid_scroll", "message": "Use um valor entre -20 e 20, diferente de zero."}]
    navigator._gui().scroll(amount)
    return _content(_observe_after_action({"success": True, "status": "scrolled", "amount": amount}))


_ALLOWED_KEYS = {
    "enter", "tab", "esc", "escape", "space", "backspace", "delete",
    "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}


@mcp.tool(structured_output=False)
@tracked_action("Pressionando tecla")
def press_key(key: str) -> list[Any]:
    """Press one navigation key from the safe list and return a fresh screenshot."""
    normalized = key.strip().lower()
    if normalized not in _ALLOWED_KEYS:
        return [{
            "success": False,
            "status": "unsupported_key",
            "allowed_keys": sorted(_ALLOWED_KEYS),
        }]
    navigator._gui().press(normalized)
    return _content(_observe_after_action({"success": True, "status": "key_pressed", "key": normalized}))


@mcp.tool()
@tracked_action("Lendo ÃƒÂ¡rvore de acessibilidade")
def read_accessibility_tree(window_title_contains: str = "", max_elements: int = 120) -> dict[str, Any]:
    """Read visible Windows UI Automation elements before resorting to pixel coordinates.

    Requires optional pywinauto. Returns names, roles, automation IDs and screen rectangles.
    """
    try:
        from pywinauto import Desktop
    except ImportError:
        return {
            "success": False,
            "status": "dependency_missing",
            "message": "Instale pywinauto para leitura da ÃƒÂ¡rvore UI Automation.",
        }

    needle = window_title_contains.casefold().strip()
    limit = min(max(int(max_elements), 1), 300)
    windows = []
    for window in Desktop(backend="uia").windows():
        try:
            title = window.window_text()
            if not window.is_visible() or (needle and needle not in title.casefold()):
                continue
            elements = []
            for control in window.descendants()[:limit]:
                try:
                    info = control.element_info
                    rect = control.rectangle()
                    elements.append({
                        "name": info.name,
                        "control_type": info.control_type,
                        "automation_id": info.automation_id,
                        "enabled": bool(info.enabled),
                        "rectangle": [rect.left, rect.top, rect.right, rect.bottom],
                    })
                except Exception:
                    continue
            windows.append({"title": title, "elements": elements})
        except Exception:
            continue
    return {"success": True, "windows": windows}


# Read-only local network discovery tools; they never send active probes.
@mcp.tool()
def network_interfaces() -> dict[str, Any]:
    """List local IPv4 interfaces and candidate private subnets; no packets are sent."""
    from app.adapters.edge.network_discovery_adapter import network_interfaces as _interfaces
    return _interfaces()


@mcp.tool()
def network_discover_devices(cidr: str) -> dict[str, Any]:
    """Read the local ARP cache for an explicitly supplied private IPv4 /24 or smaller. No probes are sent."""
    from app.adapters.edge.network_discovery_adapter import discover_devices
    try:
        return discover_devices(cidr)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}


@mcp.tool()
def network_inspect_device(ip_address: str) -> dict[str, Any]:
    """Resolve reverse DNS for one RFC1918 private IPv4 address; does not scan ports or connect to it."""
    from app.adapters.edge.network_discovery_adapter import inspect_private_address
    return inspect_private_address(ip_address)

# Android navigation tools are registered additively on the same MCP server.
# Existing desktop tool implementations and their default behavior remain unchanged.
@mcp.tool()
def android_connect(pairing_address: str, pairing_code: str, device_address: str) -> dict[str, Any]:
    """Pair and connect Android Wireless debugging using the pairing endpoint/code and separate connect endpoint shown by Android Settings. Stores only the selected endpoint, never the pairing code."""
    from app.adapters.edge.android_connection_adapter import pair_and_connect
    return pair_and_connect(pairing_address, pairing_code, device_address)


@mcp.tool()
def android_device_status() -> dict[str, Any]:
    """Report ADB device states and the currently selected Android target."""
    from app.adapters.edge.android_connection_adapter import device_status
    return device_status()

def _android_navigation_adapter():
    from app.adapters.edge.android_navigation_adapter import AndroidNavigationAdapter
    return AndroidNavigationAdapter()


@mcp.tool(structured_output=False)
@tracked_action("Observando tela Android")
def android_observe_screen() -> list[Any]:
    """Observe the explicitly configured Android device; return status and a PNG image."""
    result = _android_navigation_adapter().observe_screen()
    if not result.get("success"):
        return _content(result)
    metadata = {key: value for key, value in result.items() if key != "image_base64"}
    return [
        TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False, default=str)),
        Image(data=base64.b64decode(result["image_base64"], validate=True), format="png"),
    ]


@mcp.tool()
@tracked_action("Tocando na tela Android")
def android_tap(x: int, y: int) -> dict[str, Any]:
    """Tap Android screen coordinates. Observe the screen before and after acting."""
    return _android_navigation_adapter().tap(x, y)


@mcp.tool()
@tracked_action("Deslizando na tela Android")
def android_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> dict[str, Any]:
    """Swipe on the configured Android device; coordinates must come from a fresh observation."""
    return _android_navigation_adapter().swipe(x1, y1, x2, y2, duration_ms)


@mcp.tool()
@tracked_action("Pressionando tecla Android")
def android_press_key(keycode: str) -> dict[str, Any]:
    """Press an allowlisted Android navigation key (for example HOME, BACK, or ENTER)."""
    return _android_navigation_adapter().press_key(keycode)


@mcp.tool()
@tracked_action("Digitando texto no Android")
def android_type_text(text: str) -> dict[str, Any]:
    """Type text into the currently focused Android field; maximum 2000 characters."""
    return _android_navigation_adapter().type_text(text)


if __name__ == "__main__":
    if _HTTP_TRANSPORT not in {"stdio", "streamable-http"}:
        raise SystemExit("JARVIS_DESKTOP_TRANSPORT deve ser stdio ou streamable-http.")
    mcp.run(transport=_HTTP_TRANSPORT)


