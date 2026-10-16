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
# Limite de caracteres injetados em prompts de LLM (o arquivo consolidado pode
# chegar a vários MB; prompts precisam de um teto previsível).
MAX_CONSOLIDATED_CHARS = 200_000
_TRUNCATION_NOTICE = "\n... [contexto consolidado truncado]"


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
        if context is None:
            context = {}

        config = context.get("config", {})
        action = config.get("action") or context.get("action", "read")

        if action == "read":
            context["context_content"] = self.get_context()
            context["context_loaded"] = True
            return context
        elif action == "refresh":
            self._cache = None
            context["context_content"] = self.get_context()
            return context
        elif action == "info":
            context["context_info"] = self.get_info()
            return context

        return context
    
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
            logger.error(f"[CONTEXT] Falha ao ler contexto: {e}")
            return "Arquivo de contexto não disponível."

    def get_info(self) -> Dict[str, Any]:
        """Retorna informação resumida do contexto consolidado."""
        path = self._consolidated_path
        info = {
            "consolidated_path": str(path),
            "exists": path.exists(),
        }
        if path.exists():
            try:
                info["size_bytes"] = path.stat().st_size
            except Exception:
                info["size_bytes"] = None
        return info


def load_consolidated_context(max_chars: int = MAX_CONSOLIDATED_CHARS) -> str:
    """Carrega o contexto consolidado do codebase via Nexus (autoconsciência).

    Tolerante a falhas: devolve ``""`` quando o serviço não está registrado ou o
    arquivo consolidado ainda não foi gerado, para não bloquear quem consome
    (EvolutionOrchestrator, JarvisDevAgent). Conteúdos maiores que *max_chars*
    são truncados antes de ir para o prompt do LLM.
    """
    from app.core.nexus import nexus  # import tardio: evita ciclo de importação

    try:
        service = nexus.resolve("consolidated_context_service")
    except Exception as exc:
        logger.debug("[CONTEXT] consolidated_context_service indisponível: %s", exc)
        return ""

    if service is None:
        return ""

    # can_execute() já sinaliza se o arquivo consolidado existe no disco
    can_execute = getattr(service, "can_execute", None)
    if callable(can_execute):
        try:
            if not can_execute({}):
                return ""
        except Exception:
            return ""

    try:
        get_context = getattr(service, "get_context", None)
        if not callable(get_context):
            return ""
        content = str(get_context() or "")
    except Exception as exc:
        logger.debug("[CONTEXT] Falha ao ler contexto consolidado: %s", exc)
        return ""

    if not content or content.startswith("Arquivo de contexto não disponível"):
        return ""
    if len(content) > max_chars:
        return content[:max_chars] + _TRUNCATION_NOTICE
    return content
