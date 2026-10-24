# -*- coding: utf-8 -*-
"""Navegação Android: traduz ações de navegação em chamadas à AdbConnection.

Não conhece MCP nem túnel. As ferramentas MCP `mobile_*` chamam este adaptador.
Usa o mesmo vocabulário de status da navegação visual do desktop.
"""

from __future__ import annotations

import base64
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from app.adapters.connection.adb_connection import AdbConnection, AdbError
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_MAX_STEPS = 20
_ACTIONS = {"tap", "type", "key", "launch", "stop", "swipe"}
Factory = Callable[[str], AdbConnection]
_BOUNDS = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


def parse_bounds(bounds: str) -> Optional[tuple[int, int, int, int]]:
    """'[x1,y1][x2,y2]' -> (x1, y1, x2, y2). None se inválido ou vazio."""
    match = _BOUNDS.match(bounds or "")
    if not match:
        return None
    x1, y1, x2, y2 = (int(v) for v in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def parse_elements(xml_text: str) -> List[Dict[str, Any]]:
    """Lista nós com resource-id, texto e centro de toque."""
    root = ET.fromstring(xml_text)
    elements: List[Dict[str, Any]] = []
    for node in root.iter("node"):
        bounds = parse_bounds(node.get("bounds", ""))
        if bounds is None:
            continue
        x1, y1, x2, y2 = bounds
        elements.append(
            {
                "resource_id": node.get("resource-id", ""),
                "text": node.get("text", ""),
                "content_desc": node.get("content-desc", ""),
                "class": node.get("class", ""),
                "clickable": node.get("clickable") == "true",
                "center": ((x1 + x2) // 2, (y1 + y2) // 2),
            }
        )
    return elements


def _matches(element: Dict[str, Any], resource_id: Optional[str], text: Optional[str]) -> bool:
    if resource_id and element["resource_id"] != resource_id:
        return False
    if text and text not in (element["text"], element["content_desc"]):
        return False
    return bool(resource_id or text)


class AndroidNavigationAdapter(NexusComponent):
    """Observa e age sobre aparelhos Android via ADB, uma ação por vez."""

    def __init__(
        self,
        connection_factory: Optional[Factory] = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__()
        self._factory: Factory = connection_factory or (lambda serial: AdbConnection(serial))
        self._sleep = sleep

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entrada Nexus: despacha pela chave `action`."""
        ctx = context or {}
        serial = ctx.get("device_id", "")
        action = ctx.get("action")
        if action == "observe":
            return self.observe(serial)
        if action == "run_recipe":
            return self.run_recipe(serial, ctx.get("steps", []))
        return {"status": "invalid_recipe", "message": f"ação desconhecida: {action}"}

    def observe(self, serial: str) -> Dict[str, Any]:
        try:
            conn = self._factory(serial)
            if not conn.is_connected():
                return {"status": "unavailable", "message": "aparelho não está autorizado/conectado"}
            png = conn.screencap_png()
            xml_text = conn.dump_hierarchy()
            elements = parse_elements(xml_text)
        except (AdbError, ET.ParseError) as exc:
            return {"status": "unavailable", "message": str(exc)}
        return {
            "status": "observed",
            "device_id": serial,
            "screenshot_png_b64": base64.b64encode(png).decode("ascii"),
            "elements": elements,
        }

    def find(self, serial: str, resource_id: Optional[str] = None, text: Optional[str] = None) -> Dict[str, Any]:
        observed = self.observe(serial)
        if observed["status"] != "observed":
            return observed
        matches = [e for e in observed["elements"] if _matches(e, resource_id, text)]
        if not matches:
            return {"status": "not_found", "device_id": serial}
        if len(matches) > 1:
            return {"status": "ambiguous", "device_id": serial, "count": len(matches)}
        return {"status": "found", "device_id": serial, "element": matches[0]}

    def run_recipe(self, serial: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executa passos em ordem. Para no primeiro passo que não se confirma.

        Passo: {target: {resource_id|text}, action, value?, verify?: {text|resource_id}}.
        Ações sem alvo (launch, key, stop) usam `value` no lugar do alvo.
        """
        if not isinstance(steps, list) or not 1 <= len(steps) <= _MAX_STEPS:
            return {"status": "invalid_recipe", "message": f"receita deve ter 1 a {_MAX_STEPS} passos"}
        try:
            conn = self._factory(serial)
            if not conn.is_connected():
                return {"status": "unavailable", "message": "aparelho não está autorizado/conectado"}
        except AdbError as exc:
            return {"status": "unavailable", "message": str(exc)}

        completed = 0
        for index, step in enumerate(steps):
            err = _validate_step(step)
            if err:
                return {"status": "invalid_recipe", "step": index, "message": err, "completed_steps": completed}
            outcome = self._run_step(serial, conn, step)
            if outcome["status"] != "completed":
                outcome.update({"step": index, "completed_steps": completed})
                return outcome
            completed += 1
        return {"status": "completed", "device_id": serial, "completed_steps": completed}

    def _run_step(self, serial: str, conn: AdbConnection, step: Dict[str, Any]) -> Dict[str, Any]:
        action = step["action"]
        try:
            if action in ("launch", "stop", "key"):
                if action == "launch":
                    conn.launch_app(step["value"])
                elif action == "stop":
                    conn.force_stop(step["value"])
                else:
                    conn.key_event(int(step["value"]))
            elif action == "type":
                conn.type_text(step["value"])
            else:  # tap
                target = self.find(serial, step["target"].get("resource_id"), step["target"].get("text"))
                if target["status"] != "found":
                    return {"status": target["status"]}
                x, y = target["element"]["center"]
                conn.tap(x, y)
        except AdbError as exc:
            return {"status": "unavailable", "message": str(exc)}

        verify = step.get("verify")
        if verify:
            self._sleep(float(step.get("wait_ms", 400)) / 1000)
            seen = self.find(serial, verify.get("resource_id"), verify.get("text"))
            if seen["status"] != "found":
                return {"status": "postcondition_failed", "device_id": serial}
        return {"status": "completed"}


def _validate_step(step: Any) -> Optional[str]:
    if not isinstance(step, dict):
        return "passo deve ser um objeto"
    action = step.get("action")
    if action not in _ACTIONS:
        return f"ação inválida: {action}"
    if action == "tap":
        target = step.get("target") or {}
        if not (target.get("resource_id") or target.get("text")):
            return "tap exige target.resource_id ou target.text"
    elif action in ("launch", "stop", "key") and not step.get("value"):
        return f"{action} exige value"
    elif action == "type" and not step.get("value"):
        return "type exige value"
    verify = step.get("verify")
    if verify is not None and not (verify.get("resource_id") or verify.get("text")):
        return "verify exige resource_id ou text"
    return None
