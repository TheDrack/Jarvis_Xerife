"""Navegação via Android usando ADB em transporte privado autorizado.

O transporte/conector MCP é independente deste adaptador. O alvo deve estar
selecionado explicitamente e já autorizado para ADB; não se presume Tailscale
nem qualquer software específico de conectividade.
"""
from __future__ import annotations

import base64
import os
import subprocess
from typing import Any


class AndroidNavigationAdapter:
    """Operações ADB mínimas para observar e operar a UI Android."""

    def __init__(self, device_address: str | None = None, adb_path: str | None = None,
                 timeout_seconds: int = 15) -> None:
        self.device_address = (device_address or os.getenv("JARVIS_ANDROID_DEVICE", "")).strip()
        self.adb_path = adb_path or os.getenv("JARVIS_ADB_PATH", "adb")
        self.timeout_seconds = max(1, min(int(timeout_seconds), 60))

    def _run(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        if not self.device_address:
            raise ValueError("Defina JARVIS_ANDROID_DEVICE com o serial/endereço ADB do dispositivo autorizado.")
        return subprocess.run(
            [self.adb_path, "-s", self.device_address, *args],
            capture_output=True, text=True, timeout=timeout or self.timeout_seconds, check=False,
        )

    def observe_screen(self) -> dict[str, Any]:
        """Capture a tela atual como PNG codificado em base64."""
        if not self.device_address:
            return {"success": False, "status": "device_not_configured"}
        try:
            proc = subprocess.run(
                [self.adb_path, "-s", self.device_address, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=self.timeout_seconds, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"success": False, "status": "transport_error", "error": str(exc)}
        if proc.returncode:
            return {"success": False, "status": "adb_error", "error": proc.stderr.decode("utf-8", "replace")[:1000]}
        if not proc.stdout:
            return {"success": False, "status": "empty_screenshot"}
        return {"success": True, "status": "observed", "device_id": self.device_address,
                "image_base64": base64.b64encode(proc.stdout).decode("ascii"), "image_format": "png"}

    def tap(self, x: int, y: int) -> dict[str, Any]:
        if x < 0 or y < 0:
            return {"success": False, "status": "invalid_coordinates"}
        return self._action("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> dict[str, Any]:
        if min(x1, y1, x2, y2) < 0 or not 50 <= duration_ms <= 5000:
            return {"success": False, "status": "invalid_swipe"}
        return self._action("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def press_key(self, keycode: str) -> dict[str, Any]:
        allowed = {"HOME", "BACK", "ENTER", "MENU", "APP_SWITCH", "DPAD_UP", "DPAD_DOWN",
                   "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER", "VOLUME_UP", "VOLUME_DOWN"}
        keycode = keycode.strip().upper()
        if keycode not in allowed:
            return {"success": False, "status": "unsupported_key", "allowed_keys": sorted(allowed)}
        return self._action("shell", "input", "keyevent", keycode)

    def type_text(self, text: str) -> dict[str, Any]:
        if len(text) > 2000:
            return {"success": False, "status": "input_too_long"}
        # Escape remote-shell metacharacters as well as Android's text escapes.
        escaped = text.replace("%", "%25").replace(" ", "%s")
        shell_metacharacters = {chr(code) for code in (92, 34, 39, 36, 96, 59, 38, 124, 60, 62, 40, 41, 91, 93, 123, 125, 42, 33, 63, 126, 35)}
        escaped = "".join((chr(92) + char) if char in shell_metacharacters else char for char in escaped)
        return self._action("shell", "input", "text", escaped)

    def _action(self, *args: str) -> dict[str, Any]:
        if not self.device_address:
            return {"success": False, "status": "device_not_configured"}
        try:
            proc = self._run(*args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"success": False, "status": "transport_error", "error": str(exc)}
        if proc.returncode:
            return {"success": False, "status": "adb_error", "error": proc.stderr[:1000]}
        return {"success": True, "status": "action_sent", "device_id": self.device_address,
                "command": list(args)}
