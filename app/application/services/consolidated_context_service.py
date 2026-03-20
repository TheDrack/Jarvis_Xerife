# -*- coding: utf-8 -*-
"""Consolidated Context Service — Serviço de contexto consolidado.
CORREÇÃO: Mantido padrão original do CORE para compatibilidade com Nexus Discovery.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

DEFAULT_CONSOLIDATED_PATH = "CORE_LOGIC_CONSOLIDATED.txt"
MAX_CONTEXT_TOKENS = 100000


class ConsolidatedContextService(NexusComponent):
    """Serviço para leitura do contexto consolidado."""
    
    def __init__(self, consolidated_path: str = DEFAULT_CONSOLIDATED_PATH):
        super().__init__()
        self._consolidated_path = Path(consolidated_path)
        self._cache: Optional[str] = None
        self._cache_version: int = 0
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return self._consolidated_path.exists()
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna o contexto mantendo as chaves originais do pipeline."""
        ctx = context if context is not None else {}
        config = ctx.get("config", {})
        action = config.get("action") or ctx.get("action", "read")
        
        if action == "read":
            ctx["context_content"] = self.get_context()
            ctx["context_loaded"] = True
            return ctx
        elif action == "refresh":
            self._cache = None
            ctx["context_content"] = self.get_context()
            return ctx
        elif action == "info":
            ctx["context_info"] = self.get_info()
            return ctx
        
        return ctx
    
    def get_context(self, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
        """Lê o arquivo consolidado respeitando o arquivo físico no disco."""
        if self._cache is not None:
            return self._cache
        
        if not self._consolidated_path.exists():
            logger.warning(f"[CONTEXT] Arquivo não encontrado: {self._consolidated_path}")
            return "Arquivo de contexto não disponível."
        
        try:
            content = self._consolidated_path.read_text(encoding="utf-8")
            if len(content) > max_tokens * 4:
                content = content[: max_tokens * 4]
            self._cache = content
            return content
        except Exception as e:
            logger.error(f