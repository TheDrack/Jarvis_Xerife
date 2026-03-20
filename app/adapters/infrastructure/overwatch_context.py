# -*- coding: utf-8 -*-
"""Overwatch Context Monitor — Monitora mudanças no contexto."""
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Any  # CORREÇÃO: 'Any' adicionado aqui
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

_CONTEXT_FILE = Path("data/context.jrvs")

class ContextMonitor:
    """Monitora mudanças no arquivo de contexto."""
    
    def __init__(self, context_path: Optional[Path] = None) -> None:
        self._context_file = context_path or _CONTEXT_FILE
        self._last_mtime: Optional[float] = None
    
    def check_changes(
        self,
        on_change_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Verifica se o contexto mudou e chama callback se mudou.
        """
        if not self._context_file.exists():
            return False
        
        try:
            mtime = self._context_file.stat().st_mtime
            
            if self._last_mtime is None:
                self._last_mtime = mtime
                return False
            
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                logger.info("[Overwatch] Contexto atualizado.")
                
                if on_change_callback:
                    on_change_callback()
                
                return True
            
            return False
        except Exception as exc:
            logger.debug("[Overwatch] Erro ao verificar contexto: %s", exc)
            return False

def load_context() -> dict:
    """Carrega o contexto atual."""
    if not _CONTEXT_FILE.exists():
        return {}
    try:
        return document_store.read(_CONTEXT_FILE)
    except Exception:
        return {}

def get_pending_tasks(limit: int = 5) -> list:
    """Retorna tarefas pendentes do contexto."""
    ctx = load_context()
    raw = ctx.get("pending_tasks", [])
    return [str(t) for t in raw[:limit]]

def update_context_field(field: str, value: Any) -> bool:
    """Atualiza um campo no contexto."""
    try:
        ctx = load_context()
        ctx[field] = value
        document_store.write(_CONTEXT_FILE, ctx)
        return True
    except Exception as exc:
        logger.debug("[Overwatch] Falha ao atualizar contexto: %s", exc)
        return False
