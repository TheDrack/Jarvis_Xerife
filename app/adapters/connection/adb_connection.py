# -*- coding: utf-8 -*-
"""Conexão ADB com um aparelho Android.

Camada de conexão pura: executa comandos adb e devolve dados. Não conhece MCP,
túnel nem banco de dados. O executor é injetável para permitir testes sem aparelho.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_MAX_TEXT = 500
# Keycodes permitidos. Lista fechada para evitar envio arbitrário de eventos.
ALLOWED_KEYCODES = {
    3: "HOME",
    4: "BACK",
    24: "VOLUME_UP",
    25: "VOLUME_DOWN",
    66: "ENTER",
    67: "DEL",
    187: "APP_SWITCH",
    223: "SLEEP",
    224: "WAKEUP",
}
# Caracteres que o shell do aparelho interpreta; são escapados com barra invertida.
_SHELL_META = set("\\\"'`$&|;<>()*?[]{}#~!")


class AdbError(RuntimeError):
    """Falha ao executar um comando adb ou entrada inválida."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[Sequence[str], float], CommandResult]


def _default_runner(argv: Sequence[str], timeout: float) -> CommandResult:
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise AdbError("adb não encontrado no PATH; defina ADB_PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"comando adb excedeu {timeout}s") from exc
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def escape_for_input_text(text: str) -> str:
    """Prepara texto para `input text` (ASCII imprimível, espaços viram %s)."""
    if not text or len(text) > _MAX_TEXT:
        raise AdbError(f"texto deve ter entre 1 e {_MAX_TEXT} caracteres")
    out: list[str] = []
    for ch in text:
        if not (32 <= ord(ch) <= 126):
            raise AdbError("input text aceita apenas ASCII imprimível")
        if ch == " ":
            out.append("%s")
        elif ch in _SHELL_META:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


class AdbConnection:
    """Conexão ADB com um único aparelho identificado pelo serial."""

    def __init__(
        self,
        serial: str,
        *,
        adb_path: str = "adb",
        runner: Optional[Runner] = None,
        timeout: float = 15.0,
    ) -> None:
        if not _SERIAL.match(serial or ""):
            raise AdbError("serial de dispositivo inválido")
        self.serial = serial
        self._adb = adb_path
        self._run = runner or _default_runner
        self._timeout = timeout

    def _argv(self, *args: str) -> list[str]:
        return [self._adb, "-s", self.serial, *args]

    def _checked(self, *args: str) -> bytes:
        result = self._run(self._argv(*args), self._timeout)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise AdbError(f"adb falhou ({result.returncode}): {detail or 'sem detalhe'}")
        return result.stdout

    def is_connected(self) -> bool:
        """True se o aparelho está no estado `device` (autorizado e pronto)."""
        try:
            result = self._run(self._argv("get-state"), self._timeout)
        except AdbError:
            return False
        return result.returncode == 0 and result.stdout.strip() == b"device"

    def screencap_png(self) -> bytes:
        data = self._checked("exec-out", "screencap", "-p")
        if not data.startswith(b"\x89PNG"):
            raise AdbError("screencap não retornou PNG")
        return data

    def dump_hierarchy(self) -> str:
        """XML da hierarquia de UI via uiautomator (sem instalar APK)."""
        raw = self._checked("shell", "uiautomator", "dump", "/dev/tty").decode("utf-8", "replace")
        start = raw.find("<?xml")
        if start < 0:
            start = raw.find("<hierarchy")
        if start < 0:
            raise AdbError("uiautomator não devolveu hierarquia XML")
        return raw[start:].strip()

    def tap(self, x: int, y: int) -> None:
        _check_point(x, y)
        self._checked("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        _check_point(x1, y1)
        _check_point(x2, y2)
        if not 1 <= duration_ms <= 5000:
            raise AdbError("duração do gesto deve estar entre 1 e 5000 ms")
        self._checked("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def type_text(self, text: str) -> None:
        self._checked("shell", "input", "text", escape_for_input_text(text))

    def key_event(self, keycode: int) -> None:
        if keycode not in ALLOWED_KEYCODES:
            raise AdbError(f"keycode {keycode} não está na lista permitida")
        self._checked("shell", "input", "keyevent", str(keycode))

    def launch_app(self, package: str) -> None:
        _check_package(package)
        self._checked(
            "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"
        )

    def force_stop(self, package: str) -> None:
        _check_package(package)
        self._checked("shell", "am", "force-stop", package)


def _check_point(x: int, y: int) -> None:
    if not isinstance(x, int) or not isinstance(y, int) or x < 0 or y < 0:
        raise AdbError("coordenadas devem ser inteiros não negativos")


def _check_package(package: str) -> None:
    if not _PACKAGE.match(package or ""):
        raise AdbError("nome de pacote Android inválido")
