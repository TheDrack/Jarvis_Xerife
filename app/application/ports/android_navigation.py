"""Port isolado para operações explícitas de navegação Android.

Este contrato não altera VisualNavigationPort nem DeviceControlPort.
"""
from __future__ import annotations

from typing import Any, Protocol


class AndroidNavigationPort(Protocol):
    """Operações primitivas sobre um dispositivo Android autorizado."""

    def observe_screen(self) -> dict[str, Any]:
        """Retorna estado e imagem atual da tela."""
        ...

    def tap(self, x: int, y: int) -> dict[str, Any]:
        """Toca em coordenadas observadas recentemente."""
        ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350) -> dict[str, Any]:
        """Executa um gesto de deslize."""
        ...

    def press_key(self, keycode: str) -> dict[str, Any]:
        """Pressiona uma tecla de navegação permitida."""
        ...

    def type_text(self, text: str) -> dict[str, Any]:
        """Digita texto no campo atualmente focado."""
        ...
