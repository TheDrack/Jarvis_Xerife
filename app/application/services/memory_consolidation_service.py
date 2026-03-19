# -*- coding: utf-8 -*-
"""Memory Consolidation Service - A ponte entre curto e longo prazo.
CORREÇÃO: Lógica de recuperação atômica para evitar duplicação de memórias.
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class MemoryConsolidationService(NexusComponent):
    """
    Orquestra a transferência de contexto da RAM para o Banco Vetorial.
    
    Analogia Biológica:
    - WorkingMemory = Hipocampo (memória de curto prazo)
    - VectorMemory = Córtex (memória de longo prazo)
    - Este serviço = Sono (consolidação)
    """
    
    def __init__(
        self, 
        working_memory: Optional[Any] = None,
        vector_adapter: Optional[Any] = None
    ):
        super().__init__()
        self._working_memory = working_memory
        self._vector_adapter = vector_adapter
    
    def _get_working_memory(self) -> Any:
        """Resolução preguiçosa (Lazy loading) via Nexus."""
        if self._working_memory is None:
            self._working_memory = nexus.resolve("working_memory")
        return self._working_memory
    
    def _get_vector_adapter(self) -> Any:
        """Resolução preguiçosa (Lazy loading) via Nexus."""
        if self._vector_adapter is None:
            self._vector_adapter = nexus.resolve("vector_memory_adapter")
        return self._vector_adapter
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract: verifica se as dependências básicas existem."""
        return (
            self._get_working_memory() is not None and 
            self._get_vector_adapter() is not None
        )
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ponto de entrada para execução via barramento de comando Nexus."""
        ctx = context or {}
        max_age_hours = ctx.get("max_age_hours", 24)
        
        try:
            consolidated_count = self.consolidate_memories(max_age_hours)
            return {
                "success": True, 
                "consolidated_count": consolidated_count,
                "message": f"{consolidated_count} memórias transformadas em longo prazo."
            }
        except Exception as e:
            logger.error(f"[ConsolidationService] Falha na ponte de memória: {e}")
            return {"success": False, "error": str(e)}

    def consolidate_memories(self, max_age_hours: int = 24) -> int:
        """
        Puxa memórias expiradas e injeta no vetor com proteção contra duplicação.
        """
        working_memory = self._get_working_memory()
        vector_adapter = self._get_vector_adapter()
        
        if not working_memory or not vector_adapter:
            logger.warning("[ConsolidationService] Dependências (WorkingMemory/VectorAdapter) ausentes.")
            return 0
        
        # 1. Extração: Remove memórias antigas da fila volátil
        evicted_entries, _ = working_memory._evict_old_entries(max_age_hours=max_age_hours)
        
        if not evicted_entries:
            return 0
            
        consolidated = 0
        failed_entries = []

        # 2. Processamento Serial com Tratamento de Erro Individual
        for entry in evicted_entries:
            try:
                # Transformação Semântica
                user_input = entry.get("user_input", "")
                response = entry.get("response", "")
                timestamp = entry.get("_ts", "")
                
                meta = {k: v for k, v in entry.items() if k not in ["user_input", "response", "_ts"]}
                meta["source"] = "working_memory_consolidation"
                meta["original_timestamp"] = timestamp
                
                semantic_text = (
                    f"Contexto Histórico ({timestamp}):\n"
                    f"Usuário: {user_input}\n"
                    f"Jarvis: {response}"
                )
                
                # 3. Persistência
                vector_adapter.store_event(
                    text=semantic_text,
                    metadata=meta
                )
                consolidated += 1
                
            except Exception as e:
                logger.error(f"[ConsolidationService] Erro ao consolidar entrada: {e}")
                # Guardamos a entrada para reinserção na WorkingMemory
                failed_entries.append(entry)

        # 4. Recuperação (Fallback): Apenas as que falharam voltam para a fila
        if failed_entries:
            logger.warning(f"[ConsolidationService] {len(failed_entries)} falhas. Devolvendo à WorkingMemory.")
            for entry in failed_entries:
                working_memory.push(entry)
        
        if consolidated > 0:
            logger.info(f"🧠 [ConsolidationService] {consolidated} memórias consolidadas com sucesso.")
            
        return consolidated
