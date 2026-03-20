# -*- coding: utf-8 -*-
"""Overwatch Inactivity Monitor — Monitora inatividade do usuário."""
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Callable
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

class InactivityMonitor:
    """Monitora inatividade do usuário e sugere tarefas pendentes."""

    def __init__(
        self,
        timeout_seconds: int = 1800,
        check_interval_seconds: int = 60,
    ) -> None:
        self._timeout = timeout_seconds
        self._last_activity = time.monotonic()

    def reset_timer(self) -> None:
        """Reseta o timer de inatividade."""
        self._last_activity = time.monotonic()

    def check_inactivity(
        self,
        suggest_task_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Verifica se há inatividade e sugere tarefa se necessário.
        
        Returns:
            True se inatividade detectada, False caso contrário.
        """
        elapsed = time.monotonic() - self._last_activity
        if elapsed < self._timeout:
            return False

        logger.info(
            "[Overwatch] Inatividade de %.0f min detectada.",
            elapsed / 60,
        )

        if suggest_task_callback:
            suggest_task_callback()
            
        # CORREÇÃO: Alinhamento corrigido para resetar após detecção
        self._last_activity = time.monotonic()
        return True


def check_user_inactivity(
    timeout_sec: int = 1800,
    last_activity: Optional[float] = None,
) -> bool:
    """Verifica inatividade do usuário de forma standalone."""
    if last_activity is None:
        return False

    elapsed = time.monotonic() - last_activity
    return elapsed >= timeout_sec


def suggest_pending_task() -> None:
    """Sugere tarefa pendente do contexto."""
    try:
        from app.utils.document_store import document_store
        from pathlib import Path

        context_file = Path("data/context.jrvs")
        if not context_file.exists():
            return

        ctx = document_store.read(context_file)
        pending = ctx.get("pending_tasks", [])

        if pending:
            task = pending[0]
            logger.info("📅 [Overwatch] Tarefa pendente: %s", task)
    except Exception as exc:
        logger.debug("[Overwatch] Falha ao sugerir tarefa: %s", exc)


def check_vision_presence() -> bool:
    """Verifica presença do usuário via VisionAdapter."""
    try:
        vision = nexus.resolve("vision_adapter")
        if vision:
            # CORREÇÃO: Quebra de linha para evitar erro de sintaxe mobile
            description = vision.capture_and_analyze(
                "Usuário está presente? Responda sim ou não."
            )
            return description and "sim" in description.lower()
    except Exception as exc:
        logger.debug("[Overwatch] Vision indisponível: %s", exc)
    return False

def get_pending_tasks(limit: int = 5):
    """Retorna lista de tarefas pendentes para o Overwatch."""
    # Implementação placeholder baseada na estrutura do document_store
    return []
