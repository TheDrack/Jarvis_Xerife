"""Port isolado para navegação autônoma em dispositivos Android.

Este contrato não altera VisualNavigationPort nem DeviceControlPort.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class AndroidNavigationPort(Protocol):
    """Executa tarefas de UI Android em um dispositivo explicitamente selecionado."""

    def run_task(
        self,
        instruction: str,
        device_id: str,
        profile: str = "pro",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executa uma tarefa e devolve resultado estruturado e rastreável."""
        ...
