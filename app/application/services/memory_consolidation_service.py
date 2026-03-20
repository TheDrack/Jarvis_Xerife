# -*- coding: utf-8 -*-
"""Memory Consolidation Service — Ponte entre curto e longo prazo.
CORREÇÃO: Health check do VectorAdapter antes de ejetar memórias.
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


class MemoryConsolidationService(NexusComponent):
    """
    Orquestra transferência da WorkingMemory para VectorMemory.
    
    Analogia Biológica:
    - WorkingMemory = Hipocampo (curto prazo)
    - VectorMemory = Córtex (longo prazo)
    - Este serviço = Sono REM (consolidação)
    """
    
    def __init__(
        self,
        working_memory: Optional[Any] = None,
        vector_adapter: Optional[Any] = None,
    ):
        super().__init__()
        self._working_memory = working_memory
        self._vector_adapter = vector_adapter
    
    def _get_working_memory(self) -> Optional[Any]:
        """Lazy loading via Nexus."""
        if self._working_memory is None:
            try:
                self._working_memory = nexus.resolve("working_memory")
            except Exception as exc:
                logger.debug(f"[ConsolidationService] WorkingMemory indisponível: {exc}")
                return None
        return self._working_memory
    
    def _get_vector_adapter(self) -> Optional[Any]:
        """Lazy loading via Nexus."""
        if self._vector_adapter is None:
            try:
                self._vector_adapter = nexus.resolve("vector_memory_adapter")
            except Exception as exc:
                logger.debug(f"[ConsolidationService] VectorAdapter indisponível: {exc}")
                return None
        return self._vector_adapter
        def _check_vector_health(self) -> bool:
        """
        CORREÇÃO: Health check do VectorAdapter antes de consolidar.
        Returns:
            True se VectorAdapter está saudável e pronto para escrita.
        """
        vector_adapter = self._get_vector_adapter()
        
        if vector_adapter is None:
            logger.warning("[ConsolidationService] VectorAdapter não resolvido.")
            return False
        
        # Método 1: Check explícito is_healthy()
        if hasattr(vector_adapter, "is_healthy"):
            try:
                healthy = vector_adapter.is_healthy()
                if not healthy:
                    logger.warning("[ConsolidationService] VectorAdapter reportou não saudável.")
                    return False
                logger.debug("[ConsolidationService] VectorAdapter saudável (is_healthy).")
                return True
            except Exception as exc:
                logger.debug(f"[ConsolidationService] is_healthy() falhou: {exc}")
        
        # Método 2: Check de atributo _index (FAISS)
        if hasattr(vector_adapter, "_index"):
            if vector_adapter._index is None:
                logger.warning("[ConsolidationService] FAISS index não inicializado.")
                return False
            logger.debug("[ConsolidationService] FAISS index presente.")
            return True
        
        # Método 3: Check de instância (fallback puro Python)
        if hasattr(vector_adapter, "_store"):
            logger.debug("[ConsolidationService] Fallback Python ativo.")
            return True
        
        # Método 4: Teste de escrita leve (sem modificar dados permanentes)
        try:
            # Verifica se método store_event existe
            if not hasattr(vector_adapter, "store_event"):
                logger.warning("[ConsolidationService] store_event() não disponível.")
                return False
            logger.debug("[ConsolidationService] store_event() disponível.")
            return True
        except Exception as exc:
            logger.debug(f"[ConsolidationService] Health check falhou: {exc}")
            return False
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:        """NexusComponent contract."""
        working_memory = self._get_working_memory()
        vector_adapter = self._get_vector_adapter()
        
        if working_memory is None:
            logger.debug("[ConsolidationService] WorkingMemory indisponível.")
            return False
        
        if vector_adapter is None:
            logger.debug("[ConsolidationService] VectorAdapter indisponível.")
            return False
        
        return True
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa a consolidação via Nexus."""
        ctx = context or {}
        max_age_hours = ctx.get("max_age_hours", 24)
        
        try:
            count = self.consolidate_memories(max_age_hours)
            return {
                "success": True,
                "consolidated_count": count,
                "message": f"{count} memórias transformadas em longo prazo."
            }
        except Exception as e:
            logger.error(f"[ConsolidationService] Falha na consolidação: {e}")
            return {"success": False, "error": str(e)}
    
    def consolidate_memories(self, max_age_hours: int = 24) -> int:
        """
        Puxa memórias expiradas e injeta no vetor COM HEALTH CHECK.
        
        Fluxo:
        1. Health check do VectorAdapter
        2. Extração (WorkingMemory ejeta)
        3. Transformação Semântica
        4. Persistência (VectorAdapter armazena)
        5. Recuperação (se falhar, devolve para WorkingMemory)
        """
        # 0. CORREÇÃO: Health check ANTES de ejetar
        if not self._check_vector_health():
            logger.warning(
                "[ConsolidationService] VectorAdapter não saudável - "
                "adiando consolidação (memórias mantidas na WorkingMemory)."
            )
            return 0
        
        working_memory = self._get_working_memory()        vector_adapter = self._get_vector_adapter()
        
        if not working_memory or not vector_adapter:
            logger.warning("[ConsolidationService] Dependências não disponíveis.")
            return 0
        
        # 1. Extração (WorkingMemory ejeta memórias expiradas)
        try:
            evicted_entries, count = working_memory._evict_old_entries(
                max_age_hours=max_age_hours
            )
        except Exception as exc:
            logger.error(f"[ConsolidationService] Falha ao ejetar memórias: {exc}")
            return 0
        
        if not evicted_entries:
            return 0
        
        logger.info(f"[ConsolidationService] {len(evicted_entries)} memórias ejetadas para consolidação.")
        
        # 2. Transformação Semântica
        documents_to_embed = []
        for entry in evicted_entries:
            user_input = entry.get("user_input", "")
            response = entry.get("response", "")
            timestamp = entry.get("_ts", "")
            
            # Metadados limpos para busca futura
            meta = {
                k: v for k, v in entry.items()
                if k not in ["user_input", "response", "_ts"]
            }
            meta["source"] = "working_memory_consolidation"
            meta["original_timestamp"] = timestamp
            
            # Formatação para maximizar similaridade vetorial
            semantic_text = (
                f"Contexto Histórico ({timestamp}):\n"
                f"Usuário: {user_input}\n"
                f"Jarvis: {response}"
            )
            
            documents_to_embed.append({
                "text": semantic_text,
                "metadata": meta
            })
        
        # 3. Persistência (VectorAdapter armazena)
        consolidated = 0
        failed_entries = []        
        for doc in documents_to_embed:
            try:
                vector_adapter.store_event(
                    text=doc["text"],
                    metadata=doc["metadata"]
                )
                consolidated += 1
            except Exception as e:
                logger.error(f"[ConsolidationService] Falha ao gravar vetor: {e}")
                # Guarda entrada falha para recuperação
                failed_entries.append(doc)
        
        # 4. CORREÇÃO: Recuperação - devolve falhas para WorkingMemory
        if failed_entries:
            logger.warning(
                f"[ConsolidationService] {len(failed_entries)} memórias falharam - "
                "retornando para WorkingMemory (fallback)."
            )
            for doc in failed_entries:
                # Reconstrói entrada original
                original_entry = {
                    "user_input": doc["metadata"].get("user_input", ""),
                    "response": doc["metadata"].get("response", ""),
                    "_ts": doc["metadata"].get("original_timestamp", ""),
                    **{k: v for k, v in doc["metadata"].items()
                       if k not in ["source", "original_timestamp"]}
                }
                working_memory.push(original_entry)
        
        logger.info(f"🧠 [ConsolidationService] {consolidated}/{len(documents_to_embed)} memórias consolidadas.")
        return consolidated


# Compatibilidade com código legado
MemoryConsolidation = MemoryConsolidationService