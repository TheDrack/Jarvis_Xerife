# -*- coding: utf-8 -*-
"""ThoughtLogService — Gerencia logs de raciocínio e Thought Stream."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


class ThoughtLogService(NexusComponent):
    """
    Service for managing thought logs and visual feedback.
    
    Features:
    - Store internal reasoning separate from user interactions
    - Track retry counts for auto-correction cycles
    - Escalate to human after 3 failed attempts
    - Real-time visual feedback (Thought Stream with ANSI HUD)
    """
    
    MAX_RETRIES = 3
    
    def __init__(self, engine=None):
        super().__init__()
        
        # CORREÇÃO: Resolve engine via Nexus se não injetado
        if engine is not None:
            self.engine = engine
        else:
            db_adapter = nexus.resolve("db_adapter")
            self.engine = getattr(db_adapter, "engine", None) if db_adapter else None
        
        self._enabled = True
        self._max_obs_length = 500
        self._stream_to_console = True
        self._thought_history: List[Dict[str, Any]] = []
        self._mission_id: Optional[str] = None
    
    def can_execute(self, context: dict = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def configure(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Configura o serviço via dicionário."""
        if config:
            self._enabled = config.get("enabled", self._enabled)
            self._max_obs_length = config.get("max_observation_length", self._max_obs_length)
            self._stream_to_console = config.get("stream_to_console", self._stream_to_console)            mission_id = config.get("mission_id")
            if mission_id:
                self._mission_id = mission_id
    
    def execute(self, context: dict):
        """NexusComponent entry-point."""
        action = context.get("action", "stream")
        
        if action == "create_thought":
            return {"success": True, "thought": self.create_thought(**context)}
        elif action == "stream":
            return self.stream_thought(
                context.get("thought_type", "info"),
                context.get("message", ""),
                context.get("data", {})
            )
        elif action == "get_history":
            return {"success": True, "history": self.get_history(context.get("limit", 10))}
        elif action == "check_requires_human":
            return {"success": True, "requires_human": self.check_requires_human(context.get("mission_id"))}
        
        return {"success": False, "not_implemented": True}
    
    def create_thought(self, mission_id: str, session_id: str,
                       thought_process: str, **kwargs) -> Optional[Dict]:
        """Create a new thought log entry."""
        thought = {
            "thought_id": f"thought_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "mission_id": mission_id,
            "session_id": session_id,
            "thought_process": thought_process,
            "problem_description": kwargs.get("problem_description", ""),
            "success": kwargs.get("success", False),
            "error_message": kwargs.get("error_message", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self._thought_history.append(thought)
        
        if len(self._thought_history) > 100:
            self._thought_history = self._thought_history[-100:]
        
        # Tenta persistir em DB se engine disponível
        if self.engine:
            try:
                from sqlmodel import Session, select
                from app.domain.models.thought_log import ThoughtLog
                
                with Session(self.engine) as session:
                    db_thought = ThoughtLog(                        mission_id=mission_id,
                        session_id=session_id,
                        thought_process=thought_process,
                        success=kwargs.get("success", False),
                    )
                    session.add(db_thought)
                    session.commit()
            except Exception as e:
                logger.debug(f"[ThoughtLog] Falha ao persistir: {e}")
        
        return thought
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtém histórico de pensamentos."""
        return self._thought_history[-limit:]
    
    def check_requires_human(self, mission_id: str) -> bool:
        """Verifica se missão requer intervenção humana."""
        if not self.engine:
            return False
        
        try:
            from sqlmodel import Session, select
            from app.domain.models.thought_log import ThoughtLog
            
            with Session(self.engine) as session:
                statement = select(ThoughtLog).where(
                    ThoughtLog.mission_id == mission_id,
                    ThoughtLog.requires_human == True
                ).limit(1)
                result = session.exec(statement).first()
                return result is not None
        except Exception as e:
            logger.error(f"Error checking human requirement: {e}")
            return False
    
    def stream_thought(self, thought_type: str, message: str,
                       data: Optional[Dict] = None) -> Dict[str, Any]:
        """Transmite pensamento em tempo real com formatação ANSI."""
        if not self._enabled:
            return {"success": False, "error": "ThoughtLogService disabled"}
        
        if thought_type == "observation":
            if len(message) > self._max_obs_length:
                message = message[:self._max_obs_length] + "..."
        
        thought = {
            "thought_id": f"thought_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "mission_id": self._mission_id,
            "thought_type": thought_type,            "message": message,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self._thought_history.append(thought)
        
        if self._stream_to_console:
            self._render_to_console(thought)
        
        return {"success": True, "streamed": True}
    
    def _render_to_console(self, thought: Dict[str, Any]) -> None:
        """Renderiza pensamento no console com formatação ANSI."""
        import sys
        
        colors = {
            "planning": "\033[96m\033[1m",
            "action": "\033[93m\033[1m",
            "observation": "\033[92m",
            "error": "\033[91m\033[1m",
            "success": "\033[92m\033[1m",
            "info": "\033[37m\033[2m",
        }
        
        icons = {
            "planning": "🧠",
            "action": "⚡",
            "observation": "👁️",
            "error": "❌",
            "success": "✅",
            "info": "ℹ️",
        }
        
        reset = "\033[0m"
        dim = "\033[2m"
        
        thought_type = thought.get("thought_type", "info")
        message = thought.get("message", "")
        timestamp = thought.get("timestamp", "")
        
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M:%S")
        except:
            time_str = "??:??:??"
        
        color = colors.get(thought_type, "")
        icon = icons.get(thought_type, "•")
                formatted = f"{dim}[{time_str}]{reset} {color}{icon} [{thought_type.upper()}]{reset} {message}"
        print(formatted, file=sys.stdout, flush=True)
    
    def stream_planning(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought("planning", message, data)
    
    def stream_action(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought("action", message, data)
    
    def stream_observation(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought("observation", message, data)
    
    def stream_error(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought("error", message, data)
    
    def stream_success(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought("success", message, data)