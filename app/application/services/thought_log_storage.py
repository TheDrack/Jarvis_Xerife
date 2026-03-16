# -*- coding: utf-8 -*-
"""ThoughtLogService — Armazenamento e Persistência.
Versão 2026.03: Proteção de tipos e correção de parse de data.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from app.domain.models.thought_log import ThoughtLog

logger = logging.getLogger(__name__)


class ThoughtStorage:
    """Gerencia armazenamento volátil (RAM) e persistente (SQL) de pensamentos."""
    
    def __init__(self, engine=None, max_history: int = 100):
        self.engine = engine
        self.max_history = max_history
        self._history: List[Dict[str, Any]] = []
        self._mission_id: Optional[str] = None
    
    def add(self, thought: Dict[str, Any]) -> None:
        """Adiciona pensamento ao histórico e persiste se houver engine."""
        self._history.append(thought)
        
        # Mantém o histórico em memória dentro do limite
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        
        if self.engine:
            self._persist(thought)
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtém histórico recente da memória RAM."""
        return self._history[-limit:]
    
    def get_by_mission(self, mission_id: str, limit: int = 50) -> List[Dict]:
        """Filtra pensamentos da memória por missão."""
        return [
            t for t in self._history
            if t.get("mission_id") == mission_id
        ][-limit:]
    
    def clear(self) -> None:
        """Limpa histórico volátil."""
        self._history.clear()
    
    def set_mission_id(self, mission_id: Optional[str]) -> None:
        """Define ID da missão global atual."""
        self._mission_id = mission_id    

    def _persist(self, thought: Dict[str, Any]) -> None:
        """Persiste o dicionário de pensamento como um objeto ThoughtLog no DB."""
        try:
            if not self.engine:
                return
            
            # Tratamento seguro de timestamp
            raw_ts = thought.get("timestamp")
            if isinstance(raw_ts, str):
                try:
                    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = datetime.now(timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            with Session(self.engine) as session:
                # Mapeamento do dicionário para o modelo SQLModel
                db_thought = ThoughtLog(
                    mission_id=str(thought.get("mission_id", self._mission_id or "unknown")),
                    session_id=str(thought.get("session_id", "default")),
                    status=str(thought.get("thought_type", "internal_monologue")),
                    thought_process=str(thought.get("message", "")),
                    success=bool(thought.get("success", False)),
                    created_at=ts,
                    # Adicionando metadados se existirem para evitar perda de contexto
                    context_data=json.dumps(thought.get("data", {}), default=str)
                )
                session.add(db_thought)
                session.commit()
                
        except Exception as e:
            # Debug para não poluir logs de produção, mas capturar falhas de persistência
            logger.debug(f"[ThoughtStorage] Falha ao persistir no DB: {e}")
    
    def get_mission_thoughts(self, mission_id: str, limit: Optional[int] = None) -> List[ThoughtLog]:
        """Busca persistida: Obtém pensamentos do banco por missão."""
        try:
            if not self.engine:
                return []
            
            with Session(self.engine) as session:
                statement = (
                    select(ThoughtLog)
                    .where(ThoughtLog.mission_id == mission_id)
                    .order_by(ThoughtLog.created_at.asc())
                )
                if limit:
                    statement = statement.limit(limit)
                
                results = session.exec(statement).all()
                return list(results)
        except Exception as e:
            logger.error(f"Erro ao buscar pensamentos da missão {mission_id}: {e}")
            return []
    
    def check_requires_human(self, mission_id: str) -> bool:
        """Verifica sinalizadores de intervenção humana no banco."""
        try:
            if not self.engine:
                return False
            
            with Session(self.engine) as session:
                statement = (
                    select(ThoughtLog)
                    .where(ThoughtLog.mission_id == mission_id)
                    .where(ThoughtLog.requires_human == True)
                )
                result = session.exec(statement).first()
                return result is not None
        except Exception as e:
            logger.error(f"Erro ao verificar necessidade humana: {e}")
            return False
