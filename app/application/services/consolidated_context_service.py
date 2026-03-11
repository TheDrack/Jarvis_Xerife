# -*- coding: utf-8 -*-
"""
Consolidated Context Service — Fonte de Verdade para Autoconsciência do JARVIS.
Substitui buscas vetoriais por leitura direta do snapshot consolidado.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

DEFAULT_CONSOLIDATED_PATH = "CORE_LOGIC_CONSOLIDATED.txt"
MAX_CONTEXT_TOKENS = 100000  # Limite seguro para modelos com janela longa


class ConsolidatedContextService(NexusComponent):
    """
    Serviço de contexto consolidado para autoconsciência do JARVIS.
    Fornece o código-fonte completo do sistema para o LLM.
    """

    def __init__(self, consolidated_path: str = DEFAULT_CONSOLIDATED_PATH):
        super().__init__()
        self._consolidated_path = Path(consolidated_path)
        self._cache: Optional[str] = None
        self._cache_version: int = 0

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna o contexto consolidado atual."""
        ctx = context or {}
        action = ctx.get("action", "read")

        if action == "read":
            return {"success": True, "context": self.get_context()}
        elif action == "refresh":
            self._cache = None
            return {"success": True, "context": self.get_context()}
        elif action == "info":
            return {"success": True, "info": self.get_info()}

        return {"success": False, "error": "Ação desconhecida"}

    def get_context(self, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
        """
        Lê o arquivo consolidado e retorna o contexto completo.
        Usa cache para evitar leituras repetidas.
        """
        if self._cache is not None:            return self._cache

        if not self._consolidated_path.exists():
            logger.warning(f"[CONTEXT] Arquivo consolidado não encontrado: {self._consolidated_path}")
            return self._generate_fallback_context()

        try:
            content = self._consolidated_path.read_text(encoding="utf-8")

            # Limita por tokens (estimativa: 1 token ≈ 4 caracteres)
            if len(content) > max_tokens * 4:
                content = content[: max_tokens * 4]
                logger.info(f"[CONTEXT] Contexto truncado para {max_tokens} tokens")

            self._cache = content
            self._cache_version += 1
            logger.info(f"[CONTEXT] Contexto carregado: {len(content)} chars (v{self._cache_version})")
            return content

        except Exception as e:
            logger.error(f"[CONTEXT] Erro ao ler consolidado: {e}")
            return self._generate_fallback_context()

    def get_info(self) -> Dict[str, Any]:
        """Retorna metadados sobre o contexto consolidado."""
        if not self._consolidated_path.exists():
            return {"exists": False, "error": "Arquivo não encontrado"}

        stat = self._consolidated_path.stat()
        return {
            "exists": True,
            "path": str(self._consolidated_path),
            "size_bytes": stat.st_size,
            "size_tokens": stat.st_size // 4,
            "cached": self._cache is not None,
            "cache_version": self._cache_version,
        }

    def _generate_fallback_context(self) -> str:
        """Gera contexto fallback se o consolidado não existir."""
        return """
# JARVIS CONSOLIDATED CONTEXT — FALLBACK
# O arquivo CORE_LOGIC_CONSOLIDATED.txt não foi encontrado.
# Execute o pipeline 'sync_drive' ou o consolidator para gerar o snapshot.

## Estrutura Esperada:
- SEÇÃO 1: Mapa Estrutural (Skeleton)
- SEÇÃO 2: Conteúdo Denso (Full Logic)

## Ação Necessária:python app/runtime/pipeline_runner.py --pipeline sync_drive
"""

    def invalidate_cache(self) -> None:
        """Invalida o cache para forçar releitura."""
        self._cache = None
        logger.info("[CONTEXT] Cache invalidado")