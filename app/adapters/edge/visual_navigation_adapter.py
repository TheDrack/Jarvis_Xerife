# -*- coding: utf-8 -*-
"""Navegação visual do JARVIS por templates, com validação e recuperação segura."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.application.ports.visual_navigation import VisualNavigationPort
from app.adapters.edge.background_window_input import click_window_background
from app.adapters.edge.jarvis_agent_status import agent_activity, tracked_action
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)
_TEMPLATE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_MAX_STEPS = 20
_MAX_WATCH_SECONDS = 6
_MAX_WATCH_FPS = 2


_GUI_ACTIVITY = {
    "click": "Clique",
    "doubleClick": "Clique duplo",
    "rightClick": "Clique direito",
    "moveTo": "Movendo o cursor",
    "dragTo": "Arrastando",
    "write": "Digitando texto",
    "typewrite": "Digitando texto",
    "press": "Pressionando tecla",
    "hotkey": "Atalho de teclado",
    "keyDown": "Pressionando tecla",
    "keyUp": "Soltando tecla",
    "scroll": "Rolando a janela",
    "screenshot": "Observando tela",
    "locateOnScreen": "Procurando na tela",
    "locateAllOnScreen": "Procurando na tela",
}


class _ActivityGUI:
    """Proxy do pyautogui: toda ação de mouse, teclado ou captura aparece na caixa de status."""

    def __init__(self, gui: Any) -> None:
        self._gui = gui

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._gui, name)
        label = _GUI_ACTIVITY.get(name)
        if label is None or not callable(attr):
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with agent_activity(label):
                return attr(*args, **kwargs)

        return wrapped


class VisualNavigationAdapter(NexusComponent, VisualNavigationPort):
    """Executa receitas visuais, um clique por vez, verificando cada resultado."""

    def __init__(
        self,
        pyautogui_module: Any = None,
        template_dir: Optional[str | Path] = None,
        screenshot_dir: Optional[str | Path] = None,
    ) -> None:
        self._pyautogui = pyautogui_module
        self._tracked_gui = None
        local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / ".local" / "share"))
        self.template_dir = Path(
            template_dir or os.getenv("JARVIS_TEMPLATE_DIR", local_app_data / "Jarvis_Xerife" / "templates")
        )
        self.screenshot_dir = Path(
            screenshot_dir or local_app_data / "Jarvis_Xerife" / "visual-captures"
        )
        self.catalog_path = self.template_dir / "catalog.json"

    @tracked_action("Executando receita visual")
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        action = context.get("action", "run_visual_recipe")
        params = context.get("params", context)
        try:
            if action in ("observe_screen", "screenshot"):
                return self.observe_screen()
            if action == "watch_screen":
                return self.watch_screen(params.get("duration_seconds", 4), params.get("fps", 1))
            if action == "run_visual_recipe":
                return self.run_recipe(params.get("steps", []))
            if action == "save_visual_template":
                return self.save_template(
                    params.get("template_id", ""),
                    params.get("image_base64", ""),
                    params.get("display_name", ""),
                )
            if action == "capture_visual_template":
                return self.capture_template_from_clipboard(
                    params.get("template_id", ""),
                    params.get("display_name", ""),
                    params.get("timeout_seconds", 60),
                )
            return {"success": False, "status": "invalid_action", "message": f"Ação visual desconhecida: {action}"}
        except Exception as exc:
            logger.exception("Falha na navegação visual")
            return {
                "success": False,
                "status": "error",
                "message": str(exc),
                **self._failure_observation(),
            }

    def _gui(self) -> Any:
        if self._pyautogui is None:
            import pyautogui
            self._pyautogui = pyautogui
        self._pyautogui.FAILSAFE = True
        if self._tracked_gui is None or self._tracked_gui._gui is not self._pyautogui:
            self._tracked_gui = _ActivityGUI(self._pyautogui)
        return self._tracked_gui

    def _template_path(self, template_id: str) -> Path:
        if not _TEMPLATE_ID.fullmatch(str(template_id)):
            raise ValueError("template_id inválido; use letras, números, '_' ou '-'.")
        return self.template_dir / f"{template_id}.png"

    def _capture(self):
        return self._gui().screenshot()

    def _encode_image(self, image: Any, max_width: int = 1600) -> str:
        from PIL import Image

        if image.width > max_width:
            height = round(image.height * max_width / image.width)
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=78, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    def _save_observation(self, image: Any) -> Dict[str, str]:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.screenshot_dir / f"jarvis_{stamp}.jpg"
        image.save(path, format="JPEG", quality=82)
        return {"screenshot_path": str(path), "screenshot_data_url": self._encode_image(image)}

    @tracked_action("Observando tela")
    def observe_screen(self) -> Dict[str, Any]:
        observation = self._save_observation(self._capture())
        return {"success": True, "status": "observed", "message": "Tela capturada.", **observation}

    @tracked_action("Observando mudanças na tela")
    def watch_screen(self, duration_seconds: float = 4, fps: float = 1) -> Dict[str, Any]:
        """Retorna poucos quadros recentes para acompanhar uma mudança transitória."""
        duration = min(max(float(duration_seconds), 1), _MAX_WATCH_SECONDS)
        rate = min(max(float(fps), 0.5), _MAX_WATCH_FPS)
        interval = 1.0 / rate
        frames = []
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            image = self._capture()
            frames.append({
                "captured_at": datetime.now().astimezone().isoformat(),
                "image": self._encode_image(image),
            })
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(interval, remaining))
        return {
            "success": True,
            "status": "observed_sequence",
            "message": f"{len(frames)} quadro(s) capturados em {duration:.1f}s.",
            "frames": frames,
        }

    def _find_unique(self, image: Any, template_id: str, confidence: float = 0.88):
        import cv2  # PyAutoGUI usa OpenCV para a busca com confiança.

        path = self._template_path(template_id)
        if not path.is_file():
            return "missing_template", None
        try:
            matches = list(self._gui().locateAll(str(path), image, confidence=confidence, grayscale=True))
        except Exception as exc:
            logger.debug("Template %s não localizado: %s", template_id, exc)
            matches = []
        if not matches:
            return "not_found", None
        if len(matches) != 1:
            return "ambiguous", matches[:5]
        return "found", matches[0]

    def _failure_observation(self) -> Dict[str, str]:
        try:
            return self._save_observation(self._capture())
        except Exception as exc:
            logger.warning("Não foi possível anexar a captura atual: %s", exc)
            return {}

    @staticmethod
    def _invoke_with_timeout(control: Any, timeout_seconds: float = 1.5) -> Dict[str, Any]:
        """Bound potentially blocking UIA InvokePattern calls so one app cannot hang the bridge."""
        finished = threading.Event()
        outcome: Dict[str, Any] = {}

        def worker() -> None:
            try:
                control.invoke()
                outcome["success"] = True
            except Exception as exc:
                outcome["success"] = False
                outcome["error"] = str(exc)
            finally:
                finished.set()

        threading.Thread(target=worker, daemon=True, name="jarvis-uia-invoke").start()
        if not finished.wait(min(max(float(timeout_seconds), 0.1), 2.5)):
            return {"success": False, "status": "invoke_timeout",
                    "error": "UI Automation InvokePattern não respondeu dentro do limite."}
        return outcome

    def _invoke_accessible_at(self, x: int, y: int) -> Dict[str, Any]:
        """Invoke the unique UIA control under a visual match center, without global mouse input."""
        try:
            from pywinauto import Desktop
        except ImportError:
            return {"success": False, "status": "dependency_missing", "message": "pywinauto indisponível."}
        matches = []
        try:
            for window in Desktop(backend="uia").windows():
                try:
                    if not window.is_visible():
                        continue
                    for control in window.descendants():
                        try:
                            rect = control.rectangle()
                            if not control.is_visible() or not control.is_enabled():
                                continue
                            if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                                name = str(control.element_info.name or "").strip()
                                role = str(control.element_info.control_type or "").strip()
                                if name and role:
                                    area = max(1, (rect.right - rect.left) * (rect.bottom - rect.top))
                                    matches.append((area, window.window_text(), control, rect, name, role))
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as exc:
            return {"success": False, "status": "accessibility_error", "message": str(exc)}
        if not matches:
            return {"success": False, "status": "no_accessible_control_at_point",
                    "message": "O centro do template não corresponde a um controle acessível; nenhum clique físico foi enviado."}
        # Prefer the smallest containing rectangle (the most specific semantic control).
        matches.sort(key=lambda item: item[0])
        smallest = matches[0][0]
        best = [item for item in matches if item[0] == smallest]
        if len(best) != 1:
            return {"success": False, "status": "ambiguous_accessible_control",
                    "message": "Mais de um controle igualmente específico contém o centro do template."}
        _, title, control, rect, name, role = best[0]
        invocation = self._invoke_with_timeout(control)
        if not invocation.get("success"):
            return {"success": False, "status": invocation.get("status", "invoke_pattern_unavailable"),
                    "target_name": name, "control_type": role, "window_title": title,
                    "message": "InvokePattern falhou ou expirou; nenhum clique físico foi enviado.",
                    "detail": invocation.get("error", "")}
        return {"success": True, "status": "invoked_without_physical_mouse",
                "target_name": name, "control_type": role, "window_title": title,
                "rectangle": [rect.left, rect.top, rect.right, rect.bottom]}

    def run_recipe(self, steps: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        steps = list(steps or [])
        if not steps:
            return {"success": False, "status": "invalid_recipe", "message": "A receita precisa ter ao menos um passo."}
        if len(steps) > _MAX_STEPS:
            return {"success": False, "status": "invalid_recipe", "message": f"Máximo de {_MAX_STEPS} passos por receita."}

        completed = []
        for index, step in enumerate(steps):
            template_id = str(step.get("template_id", ""))
            verify_id = str(step.get("verify_template_id", ""))
            target_name = str(step.get("target_name", "")).strip()
            expected_name = str(step.get("expected_name_after", "")).strip()
            confidence = min(max(float(step.get("confidence", 0.88)), 0.65), 0.99)
            if not verify_id and not expected_name:
                return {
                    "success": False,
                    "status": "invalid_recipe",
                    "step": index,
                    "message": "Cada passo precisa de verify_template_id ou expected_name_after para validar a pós-ação.",
                }

            # Adaptive first choice: semantic UI Automation invokes without moving
            # the physical pointer. Only a semantic not_found may fall back to vision.
            if target_name and expected_name:
                semantic = self.click_accessibility(
                    target_name,
                    str(step.get("window_title_contains", "")),
                    str(step.get("control_type", "")),
                    expected_name,
                    step.get("verify_timeout_seconds", 2),
                )
                if semantic.get("success"):
                    completed.append({
                        "step": index, "strategy": "accessibility_invoke",
                        "target_name": target_name,
                        "verified_by": expected_name if expected_name else None,
                    })
                    continue
                if semantic.get("status") not in {"not_found"}:
                    return {
                        **semantic, "step": index, "completed_steps": completed,
                        "message": "Recuperação adaptativa interrompida com segurança: " + str(semantic.get("message", "")),
                    }

            image = self._capture()
            state, match = self._find_unique(image, template_id, confidence)
            if state != "found":
                reason = "template ausente" if state == "missing_template" else (
                    "template ambíguo" if state == "ambiguous" else "template não localizado"
                )
                return {
                    "success": False,
                    "status": "needs_template" if state == "missing_template" else state,
                    "step": index,
                    "requested_template_id": template_id if state == "missing_template" else None,
                    "verify_template_id": verify_id,
                    "message": f"Interrompi antes de clicar: {reason} '{template_id}'.",
                    "completed_steps": completed,
                    **self._save_observation(image),
                }

            if step.get("action", "click") != "click":
                return {"success": False, "status": "invalid_recipe", "step": index, "message": "Somente ação click é aceita."}
            center = self._gui().center(match)
            # Publish the detected target so the click-through Jarvis reticle glides there.
            # This is visual feedback only; the actual input path remains separate.
            try:
                from app.adapters.edge.jarvis_agent_status import set_agent_cursor_target
                set_agent_cursor_target(center.x, center.y, "target")
            except Exception as exc:
                logger.debug("Indicador visual indisponível: %s", exc)
            invoked = self._invoke_accessible_at(center.x, center.y)
            action_strategy = "template_plus_uia_invoke" if invoked.get("success") else ""
            background_title = str(step.get("background_window_title_contains", "")).strip()
            if not invoked.get("success") and background_title:
                background = click_window_background(
                    background_title, center.x, center.y, coordinates_are_screen=True
                )
                if background.get("success"):
                    invoked = background
                    action_strategy = "background_window_messages"
                else:
                    invoked = {**invoked, "background_input_detail": background}
            background_used = action_strategy == "background_window_messages"
            if not invoked.get("success"):
                if not bool(step.get("allow_physical_input", False)):
                    return {
                        "success": False,
                        "status": "background_input_unavailable",
                        "step": index,
                        "message": "Acessibilidade e entrada em segundo plano falharam; nenhum clique físico foi enviado porque allow_physical_input=false.",
                        "visual_match": [center.x, center.y],
                        "detail": invoked,
                        "completed_steps": completed,
                        **self._save_observation(self._capture()),
                    }
                self._gui().click(center.x, center.y, button="left")
                action_strategy = "physical_mouse_explicit_fallback"
            wait_ms = min(max(int(step.get("wait_ms", 350)), 0), 5000)
            if wait_ms:
                time.sleep(wait_ms / 1000)

            deadline = time.monotonic() + min(max(float(step.get("verify_timeout_seconds", 2)), 0.2), 5)
            verified = False
            while time.monotonic() < deadline:
                if expected_name:
                    try:
                        from pywinauto import Desktop
                        verified = any(
                            item.is_visible()
                            and str(item.element_info.name or "").strip().casefold() == expected_name.casefold()
                            for window in Desktop(backend="uia").windows() if window.is_visible()
                            for item in window.descendants()
                        )
                    except Exception:
                        verified = False
                else:
                    after = self._capture()
                    verify_state, _ = self._find_unique(after, verify_id, confidence)
                    verified = verify_state == "found"
                if verified:
                    break
                time.sleep(0.2)

            # A background message can be accepted by Windows but ignored by the
            # application. Only after checking the postcondition do we consider
            # the opt-in physical fallback, and we never repeat a verified action.
            physical_fallback_used = False
            if not verified and background_used and bool(step.get("allow_physical_input", False)):
                self._gui().click(center.x, center.y, button="left")
                physical_fallback_used = True
                action_strategy = "background_then_physical_fallback"
                fallback_deadline = time.monotonic() + min(max(float(step.get("verify_timeout_seconds", 2)), 0.2), 5)
                while time.monotonic() < fallback_deadline:
                    if expected_name:
                        try:
                            from pywinauto import Desktop
                            verified = any(
                                item.is_visible()
                                and str(item.element_info.name or "").strip().casefold() == expected_name.casefold()
                                for window in Desktop(backend="uia").windows() if window.is_visible()
                                for item in window.descendants()
                            )
                        except Exception:
                            verified = False
                    else:
                        after = self._capture()
                        verify_state, _ = self._find_unique(after, verify_id, confidence)
                        verified = verify_state == "found"
                    if verified:
                        break
                    time.sleep(0.2)

            if not verified:
                return {
                    "success": False,
                    "status": "postcondition_failed",
                    "step": index,
                    "physical_fallback_used": physical_fallback_used,
                    "message": f"A pós-condição '{expected_name or verify_id}' não apareceu mesmo após a estratégia de entrada. Receita interrompida.",
                    "completed_steps": completed,
                    **self._save_observation(self._capture()),
                }
            completed.append({"step": index, "template_id": template_id, "verified_by": expected_name or verify_id, "strategy": action_strategy, "physical_fallback_used": physical_fallback_used})

        return {
            "success": True,
            "status": "completed",
            "message": f"Receita concluída e verificada: {len(completed)} passo(s).",
            "completed_steps": completed,
        }

    def save_template(self, template_id: str, image_base64: str, display_name: str = "") -> Dict[str, Any]:
        path = self._template_path(template_id)
        if path.exists():
            return {"success": False, "status": "template_exists", "message": f"O template '{template_id}' já existe."}
        encoded = str(image_base64 or "")
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[-1]
        if not encoded or len(encoded) > 12_000_000:
            return {"success": False, "status": "invalid_image", "message": "Imagem ausente ou maior que o limite de 9 MB."}
        from PIL import Image, ImageStat

        try:
            image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert("RGB")
        except Exception as exc:
            return {"success": False, "status": "invalid_image", "message": f"Recorte inválido: {exc}"}
        if image.width < 8 or image.height < 8:
            return {"success": False, "status": "invalid_image", "message": "Recorte pequeno demais; selecione o botão e uma pequena margem."}
        if image.width > 1200 or image.height > 800:
            return {"success": False, "status": "invalid_image", "message": "Recorte grande demais; selecione somente o botão e uma pequena margem."}
        if max(ImageStat.Stat(image).stddev) < 2.0:
            return {"success": False, "status": "invalid_image", "message": "Recorte quase uniforme; escolha uma região com detalhes visuais."}

        self.template_dir.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG")
        catalog = self._read_catalog()
        catalog[template_id] = {
            "file": path.name,
            "display_name": str(display_name or template_id)[:120],
            "width": image.width,
            "height": image.height,
            "created_at": datetime.now().astimezone().isoformat(),
        }
        temp = self.catalog_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.catalog_path)
        return {"success": True, "status": "template_saved", "message": f"Template '{template_id}' salvo para reutilização.", "template_path": str(path)}

    def capture_template_from_clipboard(
        self, template_id: str, display_name: str = "", timeout_seconds: float = 60
    ) -> Dict[str, Any]:
        """Abre o recorte do Windows e salva a imagem copiada pelo usuário."""
        self._template_path(template_id)
        if self._template_path(template_id).exists():
            return {"success": False, "status": "template_exists", "message": f"O template '{template_id}' já existe."}
        self._gui().hotkey("win", "shift", "s")
        try:
            from PIL import Image, ImageGrab
        except ImportError as exc:
            return {"success": False, "status": "dependency_missing", "message": f"Pillow indisponível: {exc}"}
        deadline = time.monotonic() + min(max(float(timeout_seconds), 5), 120)
        while time.monotonic() < deadline:
            try:
                clip = ImageGrab.grabclipboard()
                if isinstance(clip, Image.Image):
                    buffer = io.BytesIO()
                    clip.save(buffer, format="PNG")
                    return self.save_template(
                        template_id, base64.b64encode(buffer.getvalue()).decode("ascii"), display_name
                    )
            except Exception as exc:
                logger.debug("Aguardando recorte na área de transferência: %s", exc)
            time.sleep(0.4)
        return {"success": False, "status": "capture_timeout", "message": "Nenhum recorte recebido; tente novamente e confirme a captura do botão."}

    @tracked_action("Acionando controle acessível")
    def click_accessibility(
        self,
        target_name: str,
        window_title_contains: str = "",
        control_type: str = "",
        expected_name_after: str = "",
        timeout_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """Click one uniquely identified UI Automation control and verify a semantic postcondition."""
        target_name = str(target_name or "").strip()
        if not target_name:
            return {"success": False, "status": "invalid_target", "message": "target_name é obrigatório."}
        try:
            from pywinauto import Desktop
        except ImportError:
            return {"success": False, "status": "dependency_missing", "message": "Instale pywinauto para ações por acessibilidade."}

        needle = str(window_title_contains or "").casefold().strip()
        wanted_type = str(control_type or "").casefold().strip()
        candidates = []
        try:
            windows = Desktop(backend="uia").windows()
            for window in windows:
                try:
                    title = window.window_text()
                    if not window.is_visible() or (needle and needle not in title.casefold()):
                        continue
                    for control in window.descendants():
                        try:
                            info = control.element_info
                            rect = control.rectangle()
                            if not control.is_visible() or not control.is_enabled():
                                continue
                            if str(info.name or "").strip().casefold() != target_name.casefold():
                                continue
                            if wanted_type and str(info.control_type or "").casefold() != wanted_type:
                                continue
                            if rect.right <= rect.left or rect.bottom <= rect.top:
                                continue
                            candidates.append((title, control, rect))
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as exc:
            return {"success": False, "status": "accessibility_error", "message": str(exc)}

        if not candidates:
            return {"success": False, "status": "not_found", "target_name": target_name,
                    "message": "Nenhum controle visível e habilitado corresponde ao nome e filtros."}
        if len(candidates) != 1:
            return {"success": False, "status": "ambiguous", "target_name": target_name,
                    "matches": [{"window": title, "rectangle": [rect.left, rect.top, rect.right, rect.bottom]}
                                for title, _, rect in candidates[:10]],
                    "message": "Há mais de um controle correspondente; nenhum clique foi executado."}

        title, control, rect = candidates[0]
        try:
            from app.adapters.edge.jarvis_agent_status import set_agent_cursor_target
            set_agent_cursor_target((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2, "target")
        except Exception as exc:
            logger.debug("Indicador visual indisponível: %s", exc)
        # Prefer UI Automation InvokePattern: it activates the control without moving
        # the user's global mouse cursor or injecting a physical click.
        invocation = self._invoke_with_timeout(control)
        if not invocation.get("success"):
            return {"success": False, "status": invocation.get("status", "invoke_pattern_unavailable"), "target_name": target_name,
                    "window_title": title,
                    "message": "O controle foi localizado, mas InvokePattern falhou ou expirou; nenhum clique físico foi enviado.",
                    "detail": invocation.get("error", ""), **self._failure_observation()}
        input_mode = "uia_invoke_non_physical"

        expected = str(expected_name_after or "").strip()
        if expected:
            deadline = time.monotonic() + min(max(float(timeout_seconds), 0.2), 5.0)
            found_postcondition = False
            while time.monotonic() < deadline:
                try:
                    for window in Desktop(backend="uia").windows():
                        if not window.is_visible() or window.window_text() != title:
                            continue
                        for item in window.descendants():
                            try:
                                info = item.element_info
                                if item.is_visible() and str(info.name or "").strip().casefold() == expected.casefold():
                                    found_postcondition = True
                                    break
                            except Exception:
                                continue
                        if found_postcondition:
                            break
                except Exception:
                    pass
                if found_postcondition:
                    break
                time.sleep(0.15)
            if not found_postcondition:
                return {"success": False, "status": "postcondition_failed", "target_name": target_name,
                        "expected_name_after": expected, "window_title": title,
                        "message": "Clique enviado, mas o elemento semântico esperado não apareceu.",
                        **self._failure_observation()}

        return {"success": True, "status": "postcondition_verified" if expected else "invoked_unverified",
                "target_name": target_name, "window_title": title,
                "control_type": str(getattr(control.element_info, "control_type", "")),
                "rectangle": [rect.left, rect.top, rect.right, rect.bottom],
                "input_mode": input_mode,
                "expected_name_after": expected or None,
                "message": "Controle invocado sem mouse físico." if not expected else "Invocação sem mouse físico e pós-condição semântica verificada.",
                **self._failure_observation()}

    @tracked_action("Preenchendo campo acessível")
    def set_accessibility_value(
        self, target_name: str, value: str, window_title_contains: str = "",
        control_type: str = "Edit", expected_value: str = "",
    ) -> Dict[str, Any]:
        """Set an accessible text control through UIA ValuePattern, without global keyboard input."""
        target_name = str(target_name or "").strip()
        if not target_name:
            return {"success": False, "status": "invalid_target", "message": "target_name é obrigatório."}
        try:
            from pywinauto import Desktop
        except ImportError:
            return {"success": False, "status": "dependency_missing", "message": "Instale pywinauto."}
        matches = []
        needle = str(window_title_contains or "").casefold().strip()
        role = str(control_type or "").casefold().strip()
        try:
            for window in Desktop(backend="uia").windows():
                try:
                    if not window.is_visible() or (needle and needle not in window.window_text().casefold()):
                        continue
                    for control in window.descendants():
                        try:
                            info = control.element_info
                            if (control.is_visible() and control.is_enabled()
                                and str(info.name or "").strip().casefold() == target_name.casefold()
                                and (not role or str(info.control_type or "").casefold() == role)):
                                matches.append((window.window_text(), control))
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as exc:
            return {"success": False, "status": "accessibility_error", "message": str(exc)}
        if len(matches) != 1:
            return {"success": False, "status": "not_found" if not matches else "ambiguous",
                    "target_name": target_name, "match_count": len(matches),
                    "message": "Valor não definido: o campo deve ser único e visível."}
        title, control = matches[0]
        try:
            control.set_edit_text(str(value))
            actual = str(control.get_value())
        except Exception as exc:
            return {"success": False, "status": "value_pattern_unavailable", "target_name": target_name,
                    "window_title": title, "message": "Campo não suporta escrita sem teclado global.",
                    "detail": str(exc), **self._failure_observation()}
        expected = str(expected_value if expected_value else value)
        verified = actual == expected
        return {"success": verified, "status": "value_verified" if verified else "value_mismatch",
                "target_name": target_name, "window_title": title, "characters": len(str(value)),
                "input_mode": "uia_value_pattern_non_physical",
                "message": "Valor definido e conferido via UI Automation." if verified else "O valor retornado difere do esperado.",
                **self._failure_observation()}

    def _read_catalog(self) -> Dict[str, Any]:
        if not self.catalog_path.exists():
            return {}
        try:
            value = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


VisualNavigator = VisualNavigationAdapter
