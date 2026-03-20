# -*- coding: utf-8 -*-
"""Overwatch Daemon — Loop principal e orquestração."""
import logging
import threading
import time
from typing import Optional
from app.core.nexus import nexus, NexusComponent
from app.adapters.infrastructure.overwatch_resource_monitor import ResourceMonitor
from app.adapters.infrastructure.overwatch_perimeter import PerimeterMonitor
from app.adapters.infrastructure.overwatch_context import ContextMonitor
logger = logging.getLogger(__name__)
_POLL_INTERVAL = 10  # segundos
class OverwatchDaemon(NexusComponent, ResourceMonitor, PerimeterMonitor, ContextMonitor):
    """Orquestrador principal do Overwatch."""
    def __init__(self, poll_interval: float = _POLL_INTERVAL) -> None:
        super().__init__()
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_count = 0
    def execute(self, context: Optional[dict] = None) -> dict:
        """Contrato NexusComponent."""
        return {"success": True, "running": self._running, "tick": self._tick_count}
    def start(self) -> None:
        """Inicia daemon em thread separada."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="OverwatchDaemon"
        )
        self._thread.start()
        logger.info("[Overwatch] Daemon iniciado.")
    def stop(self) -> None:
        """Para o daemon."""
        self._running = False
        logger.info("[Overwatch] Daemon parado.")
    def _run_loop(self) -> None:
        """Loop principal de monitoramento."""
        logger.info("[Overwatch] Loop iniciado.")
        while self._running:
            self._tick_count += 1
            try:
                self._check_resources()
                self._check_perimeter()
                self._check_context()
            except Exception as exc:
                logger.error("[Overwatch] Erro no loop: %s", exc)
            time.sleep(self._poll_interval)
        logger.info("[Overwatch] Loop encerrado.")