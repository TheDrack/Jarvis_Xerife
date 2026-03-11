# -*- coding: utf-8 -*-
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

DEFAULT_CONSOLIDATED_PATH = "CORE_LOGIC_CONSOLIDATED.txt"
MAX_CONTEXT_TOKENS = 100000 

class ConsolidatedContextService(NexusComponent):
    def __init__(self, consolidated_path: str = DEFAULT_CONSOLIDATED_PATH):
        super().__init__()
        self._consolidated_path = Path(consolidated_path)
        self._cache: Optional[str] = None
        self._cache_version: int = 0

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retorna o contexto mantendo as chaves originais do pipeline.
        """
        # Garante que o dicionário original do pipeline persista
        ctx = context if context is not None else {}
        
        # O runner do pipeline pode passar configurações aqui
        config = ctx.get("config", {})
        action = config.get("action") or ctx.get("action", "read")

        if action == "read":
            # Adicionamos o conteúdo sem apagar o 'result' ou 'artifacts' do Consolidator
            ctx["context_content"] = self.get_context()
            ctx["context_loaded"] = True
            return ctx
            
        elif action == "refresh":
            self._cache = None
            ctx["context_content"] = self.get_context()
            return ctx
            
        elif action == "info":
            # Adiciona info ao contexto em vez de substituir o dicionário
            ctx["context_info"] = self.get_info()
            return ctx

        return ctx # Retorna o contexto íntegro mesmo se a ação for desconhecida

    def get_context(self, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
        """Lê o arquivo consolidado respeitando o arquivo físico no disco."""
        # Se o cache existe, usamos. Se não, lemos o arquivo criado pelo Consolidator.
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
            logger.error(f"[CONTEXT] Erro: {e}")
            return str(e)

    def get_info(self) -> Dict[str, Any]:
        stat = self._consolidated_path.stat() if self._consolidated_path.exists() else None
        return {
            "path": str(self._consolidated_path.absolute()),
            "exists": self._consolidated_path.exists(),
            "size": stat.st_size if stat else 0
        }
