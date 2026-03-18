# -*- coding: utf-8 -*-
"""ThoughtLogService — Armazenamento e Persistência."""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from app.core.nexus import nexus
from app.domain.models.thought_log import ThoughtLog

logger = logging.getLogger(__name__)


class ThoughtStorage:
    """Gerencia armazenamento de pensamentos."""
    
    def __init__(self, engine=None, max_history: int = 100):
        self.engine = engine
        self.max_history = max_history
        self._history: List[Dict[str, Any]] = []
        self._mission_id: Optional[str] = None
    
    def add(self, thought: Dict[str, Any]) -> None:
        """Adiciona pensamento ao histórico."""
        self._history.append(thought)
        
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        
        if self.engine:
            self._persist(thought)
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtém histórico de pensamentos."""
        return self._history[-limit:]
    
    def get_by_mission(self, mission_id: str, limit: int = 50) -> List[Dict]:
        """Obtém pensamentos de uma missão específica."""
        return [
            t for t in self._history
            if t.get("mission_id") == mission_id
        ][-limit:]
    
    def clear(self) -> None:
        """Limpa histórico de pensamentos."""
        self._history.clear()
    
    def set_mission_id(self, mission_id: Optional[str]) -> None:
        """Define ID da missão atual."""
        self._mission_id = mission_id    
    def _persist(self, thought: Dict[str, Any]) -> None:
        """Persiste pensamento em banco de dados."""
        try:
            if not self.engine:
                return
            
            with Session(self.engine) as session:
                db_thought = ThoughtLog(
                    mission_id=thought.get("mission_id", ""),
                    session_id=thought.get("session_id", "default"),
                    status=thought.get("thought_type", "internal_monologue"),
                    thought_process=thought.get("message", ""),
                    success=thought.get("success", False),
                    created_at=datetime.fromisoformat(
                        thought.get("timestamp", datetime.now(timezone.utc).isoformat())
                    ),
                )
                session.add(db_thought)
                session.commit()
                
        except Exception as e:
            logger.debug(f"[ThoughtStorage] Falha ao persistir: {e}")
    
    def get_mission_thoughts(self, mission_id: str, limit: int = None) -> List[ThoughtLog]:
        """Obtém pensamentos do banco por missão."""
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
                return session.exec(statement).all()
        except Exception as e:
            logger.error(f"Error getting mission thoughts: {e}")
            return []
    
    def check_requires_human(self, mission_id: str) -> bool:
        """Verifica se missão requer intervenção humana."""
        try:
            if not self.engine:
                return False
            
            with Session(self.engine) as session:                statement = (
                    select(ThoughtLog)
                    .where(ThoughtLog.mission_id == mission_id)
                    .where(ThoughtLog.requires_human == True)
                    .limit(1)
                )
                result = session.exec(statement).first()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking human requirement: {e}")
            return False