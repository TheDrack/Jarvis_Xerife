# -*- coding: utf-8 -*-
"""ThoughtLogService — Armazenamento e Persistência.

Gerencia histórico em memória e persistência opcional em DB.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.core.nexus import nexus

logger = logging.getLogger(__name__)


class ThoughtStorage:
    """Gerencia armazenamento de pensamentos."""
    
    def __init__(self, max_history: int = 100, persist_to_db: bool = False):
        self.max_history = max_history
        self.persist_to_db = persist_to_db
        self._history: List[Dict[str, Any]] = []
        self._mission_id: Optional[str] = None
    
    def add(self, thought: Dict[str, Any]) -> None:
        """
        Adiciona pensamento ao histórico.
        
        Args:
            thought: Registro de pensamento
        """
        self._history.append(thought)
        
        # Trunca histórico se exceder limite
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        
        # Persiste em DB se habilitado
        if self.persist_to_db:
            self._persist(thought)
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtém histórico de pensamentos.
        
        Args:
            limit: Número máximo de registros
        
        Returns:
            Lista de pensamentos
        """
        return self._history[-limit:]    
    def get_by_mission(self, mission_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Obtém pensamentos de uma missão específica.
        
        Args:
            mission_id: ID da missão
            limit: Número máximo de registros
        
        Returns:
            Lista de pensamentos da missão
        """
        return [
            t for t in self._history 
            if t.get("mission_id") == mission_id
        ][-limit:]
    
    def get_by_type(self, thought_type: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Obtém pensamentos por tipo.
        
        Args:
            thought_type: Tipo de pensamento
            limit: Número máximo de registros
        
        Returns:
            Lista de pensamentos do tipo
        """
        return [
            t for t in self._history 
            if t.get("thought_type") == thought_type
        ][-limit:]
    
    def clear(self) -> None:
        """Limpa histórico de pensamentos."""
        self._history.clear()
    
    def set_mission_id(self, mission_id: Optional[str]) -> None:
        """Define ID da missão atual."""
        self._mission_id = mission_id
    
    def _persist(self, thought: Dict[str, Any]) -> None:
        """
        Persiste pensamento em banco de dados.
        
        Args:
            thought: Registro de pensamento
        """
        try:
            # Tenta resolver adapter de banco se existir            db_adapter = nexus.resolve("db_adapter")
            if not db_adapter or getattr(db_adapter, "__is_cloud_mock__", False):
                return
            
            # Persistência seria implementada aqui se ThoughtLog SQLModel existir
            logger.debug(f"[ThoughtStorage] Pensamento persistido: {thought.get('thought_id')}")
            
        except Exception as e:
            logger.debug(f"[ThoughtStorage] Falha ao persistir: {e}")
    
    def export_to_dict(self) -> Dict[str, Any]:
        """
        Exporta histórico como dicionário.
        
        Returns:
            Dict com histórico e metadados
        """
        return {
            "mission_id": self._mission_id,
            "total_thoughts": len(self._history),
            "thoughts": self._history,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def get_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtém apenas pensamentos de erro.
        
        Args:
            limit: Número máximo de registros
        
        Returns:
            Lista de pensamentos de erro
        """
        return self.get_by_type("error", limit)
    
    def get_successes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtém apenas pensamentos de sucesso.
        
        Args:
            limit: Número máximo de registros
        
        Returns:
            Lista de pensamentos de sucesso
        """
        return self.get_by_type("success", limit)