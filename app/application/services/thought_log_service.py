# -*- coding: utf-8 -*-
"""ThoughtLogService — Gerencia logs de raciocínio e Thought Stream."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select
from app.core.nexus import NexusComponent, nexus
from app.domain.models.thought_log import InteractionStatus, ThoughtLog
from .thought_log_types import ThoughtType, DEFAULT_CONFIG
from .thought_log_renderer import ThoughtRenderer
from .thought_log_storage import ThoughtStorage

logger = logging.getLogger(__name__)


class ThoughtLogService(NexusComponent):
    """
    Service for managing thought logs and visual feedback.
    
    Features:
    - Store internal reasoning separate from user interactions
    - Track retry counts for auto-correction cycles
    - Escalate to human after 3 failed attempts
    - Generate consolidated logs for commander review
    - Real-time visual feedback (Thought Stream with ANSI HUD)
    """
    
    MAX_RETRIES = 3
    
    def __init__(self, engine=None):
        super().__init__()
        config = DEFAULT_CONFIG.copy()
        
        if engine is not None:
            self.engine = engine
        else:
            db_adapter = nexus.resolve("db_adapter")
            self.engine = getattr(db_adapter, "engine", None) if db_adapter else None
        
        self._enabled = config["enabled"]
        self._max_obs_length = config["max_observation_length"]
        self._stream_to_console = config["stream_to_console"]
        
        self._renderer = ThoughtRenderer(
            color_enabled=config["color_enabled"],
            show_timestamp=config["show_timestamp"]
        )
        self._storage = ThoughtStorage(
            engine=self.engine,            max_history=config["max_history"]
        )
    
    def execute(self, context: dict):
        """NexusComponent entry-point."""
        action = context.get("action", "create_thought")
        
        if action == "create_thought":
            return {"success": True, "thought": self.create_thought(**context)}
        elif action == "stream":
            return self.stream_thought(
                context.get("thought_type", "info"),
                context.get("message", ""),
                context.get("data", {})
            )
        elif action == "get_mission_thoughts":
            return {"success": True, "thoughts": self.get_mission_thoughts(
                context.get("mission_id"), context.get("limit")
            )}
        elif action == "check_requires_human":
            return {"success": True, "requires_human": self.check_requires_human(
                context.get("mission_id")
            )}
        
        return {"success": False, "not_implemented": True}
    
    def create_thought(self, mission_id: str, session_id: str,
                       thought_process: str, **kwargs) -> Optional[ThoughtLog]:
        """Create a new thought log entry."""
        try:
            with Session(self.engine) as session:
                retry_count = self._get_mission_retry_count(session, mission_id)
                
                requires_human = False
                escalation_reason = ""
                
                if not kwargs.get("success", False) and retry_count >= self.MAX_RETRIES:
                    requires_human = True
                    escalation_reason = (
                        f"Auto-correction failed {self.MAX_RETRIES} times. "
                        "Human intervention required."
                    )
                
                thought_log = ThoughtLog(
                    mission_id=mission_id,
                    session_id=session_id,
                    status=kwargs.get("status", InteractionStatus.INTERNAL_MONOLOGUE.value),
                    thought_process=thought_process,
                    problem_description=kwargs.get("problem_description", ""),
                    solution_attempt=kwargs.get("solution_attempt", ""),                    success=kwargs.get("success", False),
                    error_message=kwargs.get("error_message", ""),
                    retry_count=retry_count if not kwargs.get("success", False) else 0,
                    context_data=json.dumps(kwargs.get("context_data", {})),
                    requires_human=requires_human,
                    escalation_reason=escalation_reason,
                    system_state=json.dumps(kwargs.get("system_state", {})),
                    discarded_alternatives=json.dumps(
                        kwargs.get("discarded_alternatives", [])
                    ),
                    expected_result=kwargs.get("expected_result", ""),
                    actual_result=kwargs.get("actual_result", ""),
                    reward_received=kwargs.get("reward_received", 0.0),
                    reward_value=kwargs.get("reward_received", 0.0),
                )
                
                session.add(thought_log)
                session.commit()
                session.refresh(thought_log)
                
                # Index na memória vetorial
                try:
                    vector_memory = nexus.resolve("vector_memory_adapter")
                    if vector_memory:
                        vector_memory.execute({
                            "action": "store",
                            "text": f"[{kwargs.get('status', 'internal')}] {thought_process}",
                            "metadata": {"mission_id": mission_id},
                        })
                except Exception as exc:
                    logger.debug("Falha ao indexar thought: %s", exc)
                
                return thought_log
                
        except Exception as e:
            logger.error(f"Error creating thought log: {e}")
            return None
    
    def _get_mission_retry_count(self, session: Session, mission_id: str) -> int:
        """Get the number of failed attempts for a mission."""
        statement = (
            select(ThoughtLog)
            .where(ThoughtLog.mission_id == mission_id)
            .where(ThoughtLog.success == False)
        )
        return len(session.exec(statement).all())
    
    def get_mission_thoughts(self, mission_id: str, limit: int = None) -> List[ThoughtLog]:
        """Get all thought logs for a specific mission."""
        return self._storage.get_mission_thoughts(mission_id, limit)    
    def check_requires_human(self, mission_id: str) -> bool:
        """Check if a mission requires human intervention."""
        return self._storage.check_requires_human(mission_id)
    
    def stream_thought(self, thought_type: str, message: str,
                        Optional[Dict] = None) -> Dict[str, Any]:
        """Transmite pensamento em tempo real com formatação ANSI."""
        if not self._enabled:
            return {"success": False, "error": "ThoughtLogService disabled"}
        
        if thought_type == ThoughtType.OBSERVATION:
            if len(message) > self._max_obs_length:
                message = message[:self._max_obs_length] + "..."
        
        thought = {
            "thought_id": f"thought_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "mission_id": self._storage._mission_id,
            "thought_type": thought_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self._storage.add(thought)
        
        if self._stream_to_console:
            self._renderer.print(thought)
        
        return {"success": True, "streamed": True}
    
    def stream_planning(self, message: str,  Optional[Dict] = None):
        return self.stream_thought(ThoughtType.PLANNING, message, data)
    
    def stream_action(self, message: str,  Optional[Dict] = None):
        return self.stream_thought(ThoughtType.ACTION, message, data)
    
    def stream_observation(self, message: str,  Optional[Dict] = None):
        return self.stream_thought(ThoughtType.OBSERVATION, message, data)
    
    def stream_error(self, message: str,  Optional[Dict] = None):
        return self.stream_thought(ThoughtType.ERROR, message, data)
    
    def stream_success(self, message: str, data: Optional[Dict] = None):
        return self.stream_thought(ThoughtType.SUCCESS, message, data)
    
    def can_execute(self, context: dict = None) -> bool:
        return True