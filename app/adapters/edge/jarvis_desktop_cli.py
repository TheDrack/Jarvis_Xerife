# -*- coding: utf-8 -*-
"""One-shot bridge for MCP hosts that can run commands but cannot attach a child MCP.

Usage:
  python app/adapters/edge/jarvis_desktop_cli.py --request path/to/request.json
  python app/adapters/edge/jarvis_desktop_cli.py --serve

The persistent mode reads one JSON object per input line and writes one result
per line. Screenshot paths can be opened with the host's image-aware file tool.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from datetime import datetime
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from app.adapters.edge.visual_navigation_adapter import VisualNavigationAdapter
from app.adapters.edge.jarvis_agent_status import tracked_action


_ALLOWED_KEYS = {
    "enter", "tab", "esc", "escape", "space", "backspace", "delete",
    "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
    *(f"f{i}" for i in range(1, 13)),
}


def _with_screenshot(navigator: VisualNavigationAdapter, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("screenshot_path"):
        return result
    observation = navigator.observe_screen()
    return {**observation, **result}


def _compact_accessibility_snapshot(windows: list[dict[str, Any]], max_elements: int = 80, max_chars: int = 12000) -> dict[str, Any]:
    """Build a bounded, text-first UI summary; element IDs are display-only per snapshot."""
    max_elements = min(max(int(max_elements), 1), 200)
    max_chars = min(max(int(max_chars), 1000), 24000)
    compact_windows = []
    remaining = max_elements
    chars_used = 0
    for window_index, window in enumerate(windows, start=1):
        title = str(window.get("title", "")).strip()
        compact_elements = []
        for element in window.get("elements", []):
            if remaining <= 0:
                break
            name = str(element.get("name", "")).strip()
            role = str(element.get("control_type", "")).strip()
            automation_id = str(element.get("automation_id", "")).strip()
            if not (name or automation_id):
                continue
            item = {"id": f"w{window_index}-e{max_elements - remaining + 1}",
                    "role": role or "Unknown", "name": name[:240],
                    "enabled": bool(element.get("enabled", False))}
            if automation_id:
                item["automation_id"] = automation_id[:120]
            size = len(json.dumps(item, ensure_ascii=False))
            if chars_used + size > max_chars:
                break
            compact_elements.append(item)
            chars_used += size
            remaining -= 1
        if compact_elements:
            compact_windows.append({"title": title[:240], "elements": compact_elements})
        if remaining <= 0 or chars_used >= max_chars:
            break
    return {"success": True, "status": "semantic_ui_snapshot",
            "id_scope": "display_only_this_snapshot",
            "instruction": "IDs are display-only. Act by unique accessible name/role and verify the resulting state.",
            "window_count": len(compact_windows),
            "element_count": sum(len(w["elements"]) for w in compact_windows),
            "windows": compact_windows,
            "truncated": remaining <= 0 or chars_used >= max_chars}


def _watch(navigator: VisualNavigationAdapter, request: dict[str, Any]) -> dict[str, Any]:
    from PIL import Image, ImageDraw

    result = navigator.watch_screen(
        request.get("duration_seconds", 3), request.get("fps", 1)
    )
    frame_paths = []
    thumbnails = []
    navigator.screenshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    frames = result.pop("frames", [])
    for index, frame in enumerate(frames, start=1):
        data_url = str(frame.get("image", ""))
        if not data_url.startswith("data:image/") or "," not in data_url:
            continue
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        path = navigator.screenshot_dir / f"jarvis_watch_{stamp}_{index:02d}.jpg"
        path.write_bytes(raw)
        frame_paths.append(str(path))
        with Image.open(io.BytesIO(raw)) as source:
            thumb = source.convert("RGB")
            thumb.thumbnail((640, 360), Image.Resampling.LANCZOS)
            thumbnails.append((str(frame.get("captured_at", index)), thumb.copy()))

    contact_sheet_path = None
    if len(thumbnails) == 1:
        contact_sheet_path = frame_paths[0]
    elif thumbnails:
        columns = min(3, len(thumbnails))
        rows = (len(thumbnails) + columns - 1) // columns
        cell_width, image_height, label_height = 640, 360, 28
        sheet = Image.new(
            "RGB", (columns * cell_width, rows * (image_height + label_height)),
            color=(24, 24, 24),
        )
        draw = ImageDraw.Draw(sheet)
        for position, (captured_at, thumb) in enumerate(thumbnails):
            x = (position % columns) * cell_width
            y = (position // columns) * (image_height + label_height)
            sheet.paste(thumb, (x, y + label_height))
            draw.text((x + 8, y + 7), captured_at[:32], fill=(255, 255, 255))
        contact_path = navigator.screenshot_dir / f"jarvis_watch_{stamp}_contact.jpg"
        sheet.save(contact_path, format="JPEG", quality=78, optimize=True)
        contact_sheet_path = str(contact_path)

    result["frame_paths"] = frame_paths
    result["contact_sheet_path"] = contact_sheet_path
    result["frame_count"] = len(frame_paths)
    return result


def _run_untracked(
    request: dict[str, Any], navigator: VisualNavigationAdapter | None = None
) -> dict[str, Any]:
    navigator = navigator or VisualNavigationAdapter()
    action = str(request.get("action", "")).strip()

    if action == "observe":
        return navigator.observe_screen()
    if action == "watch":
        return _watch(navigator, request)
    if action == "list_templates":
        return {"success": True, "status": "listed", "templates": navigator._read_catalog()}
    if action == "click_accessibility":
        return _with_screenshot(navigator, navigator.click_accessibility(
            str(request.get("target_name", "")),
            str(request.get("window_title_contains", "")),
            str(request.get("control_type", "")),
            str(request.get("expected_name_after", "")),
            request.get("timeout_seconds", 2.0),
        ))
    if action == "set_accessibility_value":
        return _with_screenshot(navigator, navigator.set_accessibility_value(
            str(request.get("target_name", "")),
            str(request.get("value", "")),
            str(request.get("window_title_contains", "")),
            str(request.get("control_type", "Edit")),
            str(request.get("expected_value", "")),
        ))
    if action in {"read_accessibility_tree", "describe_state"}:
        try:
            from pywinauto import Desktop
        except ImportError:
            return {
                "success": False, "status": "dependency_missing",
                "message": "Instale pywinauto para leitura da árvore UI Automation.",
            }
        needle = str(request.get("window_title_contains", "")).casefold().strip()
        limit = min(max(int(request.get("max_elements", 120)), 1), 300)
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
        if action == "describe_state":
            return _compact_accessibility_snapshot(windows, request.get("max_elements", 80), request.get("max_chars", 12000))
        return {"success": True, "status": "accessibility_tree", "windows": windows}
    if action == "run_recipe":
        steps = request.get("steps", [])
        return _with_screenshot(navigator, navigator.run_recipe(steps))
    if action == "capture_template":
        if request.get("user_confirmed") is not True:
            return {
                "success": False,
                "status": "confirmation_required",
                "message": "Peça autorização explícita antes de abrir o recorte do Windows.",
            }
        return navigator.capture_template_from_clipboard(
            str(request.get("template_id", "")),
            str(request.get("display_name", "")),
            request.get("timeout_seconds", 60),
        )
    if action == "click_at":
        if request.get("user_confirmed") is not True:
            return {"success": False, "status": "confirmation_required"}
        x, y = int(request["x"]), int(request["y"])
        screen = navigator._capture()
        if x < 0 or y < 0 or x >= screen.width or y >= screen.height:
            return {
                "success": False,
                "status": "coordinates_out_of_bounds",
                **navigator._save_observation(screen),
            }
        navigator._gui().click(x, y, button="left")
        return _with_screenshot(navigator, {
            "success": True, "status": "clicked",
            "target_description": str(request.get("target_description", "")),
            "x": x, "y": y,
        })
    if action == "type_text":
        value = str(request.get("text", ""))
        if len(value) > 10000:
            return {"success": False, "status": "input_too_long"}
        navigator._gui().write(value, interval=0.01)
        return _with_screenshot(navigator, {
            "success": True, "status": "typed", "characters": len(value),
        })
    if action == "press_key":
        key = str(request.get("key", "")).strip().lower()
        if key not in _ALLOWED_KEYS:
            return {"success": False, "status": "unsupported_key", "allowed_keys": sorted(_ALLOWED_KEYS)}
        navigator._gui().press(key)
        return _with_screenshot(navigator, {"success": True, "status": "key_pressed", "key": key})
    if action == "scroll":
        amount = int(request.get("amount", 0))
        if amount == 0 or abs(amount) > 20:
            return {"success": False, "status": "invalid_scroll"}
        navigator._gui().scroll(amount)
        return _with_screenshot(navigator, {"success": True, "status": "scrolled", "amount": amount})

    return {
        "success": False,
        "status": "invalid_action",
        "allowed_actions": [
            "observe", "watch", "list_templates", "read_accessibility_tree", "describe_state",
            "run_recipe", "capture_template", "click_at", "type_text", "press_key", "scroll",
        ],
    }


def run(
    request: dict[str, Any], navigator: VisualNavigationAdapter | None = None
) -> dict[str, Any]:
    """Common tracked entry point used by one-shot and persistent CLI modes."""
    action = str(request.get("action", "visual operation")).strip() or "visual operation"
    tracked = tracked_action(f"CLI: {action}")(_run_untracked)
    return tracked(request, navigator)


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep stdout small; RDM reads screenshots through its image-aware file tool."""
    output = dict(result)
    screenshot_embedded = "screenshot_data_url" in output
    output.pop("screenshot_data_url", None)
    output.pop("image_base64", None)
    output.pop("frames", None)
    output["screenshot_embedded"] = screenshot_embedded
    return output


def _serve_jsonl() -> int:
    """Keep one Python process alive and handle one JSON request per input line."""
    navigator = VisualNavigationAdapter()
    print(json.dumps({"status": "ready", "service": "jarvis_visual_navigation"}), flush=True)
    print(">>> ", end="", flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        request_id = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("A requisição precisa ser um objeto JSON.")
            request_id = request.pop("request_id", None)
            if request.get("action") == "stop":
                result = {"success": True, "status": "stopping"}
                should_stop = True
            else:
                result = _public_result(run(request, navigator))
                should_stop = False
            if request_id is not None:
                result["request_id"] = request_id
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
            if should_stop:
                return 0
            print(">>> ", end="", flush=True)
        except Exception as exc:
            error = {"success": False, "status": "error", "message": str(exc)}
            if request_id is not None:
                error["request_id"] = request_id
            print(json.dumps(error, ensure_ascii=False), flush=True)
            print(">>> ", end="", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--request", help="Path to a one-shot JSON action request.")
    mode.add_argument("--serve", action="store_true", help="Handle repeated JSONL requests in one process.")
    args = parser.parse_args()
    if args.serve:
        return _serve_jsonl()
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("A requisição precisa ser um objeto JSON.")
        print(json.dumps(_public_result(run(request)), ensure_ascii=False, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({
            "success": False, "status": "error", "message": str(exc),
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
