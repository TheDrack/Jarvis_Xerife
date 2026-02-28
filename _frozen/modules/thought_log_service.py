from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""ThoughtLogService - Manages internal reasoning logs and self-healing cycles"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.domain.models.thought_log import InteractionStatus, ThoughtLog

logger = logging.getLogger(__name__)


class ThoughtLogService(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Service for managing thought logs and implementing self-healing logic.
    
    Features:
    - Store internal reasoning separate from user interactions
    - Track retry counts for auto-correction cycles
    - Escalate to human after 3 failed attempts
    - Generate consolidated logs for commander review
    """
    
    MAX_RETRIES = 3  # Maximum retries before escalating to human
    
    def __init__(self, engine):
        """
        Initialize the ThoughtLogService
        
        Args:
            engine: SQLModel engine for database operations
        """
        self.engine = engine
    
    def create_thought(
        self,
        mission_id: str,
        session_id: str,
        thought_process: str,
        problem_description: str = "",
        solution_attempt: str = "",
        status: InteractionStatus = InteractionStatus.INTERNAL_MONOLOGUE,
        success: bool = False,
        error_message: str = "",
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[ThoughtLog]:
        """
        Create a new thought log entry
        
        Args:
            mission_id: Unique mission identifier
            session_id: Session identifier for grouping
            thought_process: Technical reasoning
            problem_description: What problem is being solved
            solution_attempt: What solution was tried
            status: Interaction status (USER_INTERACTION or INTERNAL_MONOLOGUE)
            success: Did this attempt succeed
            error_message: Error if failed
            context_data: Additional context (logs, stack traces, etc.)
            
        Returns:
            Created ThoughtLog or None if failed
        """
        try:
            with Session(self.engine) as session:
                # Get retry count for this mission
                retry_count = self._get_mission_retry_count(session, mission_id)
                
                # Check if we should escalate to human
                requires_human = False
                escalation_reason = ""
                
                if not success and retry_count >= self.MAX_RETRIES:
                    requires_human = True
                    escalation_reason = f"Auto-correction failed {self.MAX_RETRIES} times. Human intervention required."
                    logger.warning(f"Mission {mission_id} escalated to human after {retry_count} failures")
                
                thought_log = ThoughtLog(
                    mission_id=mission_id,
                    session_id=session_id,
                    status=status.value if isinstance(status, InteractionStatus) else status,
                    thought_process=thought_process,
                    problem_description=problem_description,
                    solution_attempt=solution_attempt,
                    success=success,
                    error_message=error_message,
                    retry_count=retry_count if not success else 0,
                    context_data=json.dumps(context_data or {}),
                    requires_human=requires_human,
                    escalation_reason=escalation_reason,
                )
                
                session.add(thought_log)
                session.commit()
                session.refresh(thought_log)
                
                logger.info(f"Created thought log for mission {mission_id}, retry {retry_count}")
                return thought_log
                
        except Exception as e:
            logger.error(f"Error creating thought log: {e}")
            return None
    
    def _get_mission_retry_count(self, session: Session, mission_id: str) -> int:
        """
        Get the number of failed attempts for a mission
        
        Args:
            session: Database session
            mission_id: Mission identifier
            
        Returns:
            Number of failed attempts
        """
        statement = (
            select(ThoughtLog)
            .where(ThoughtLog.mission_id == mission_id)
            .where(ThoughtLog.success == False)
        )
        failed_attempts = session.exec(statement).all()
        return len(failed_attempts)
    
    def get_mission_thoughts(
        self,
        mission_id: str,
        limit: Optional[int] = None
    ) -> List[ThoughtLog]:
        """
        Get all thought logs for a specific mission
        
        Args:
            mission_id: Mission identifier
            limit: Optional limit on number of logs
            
        Returns:
            List of thought logs
        """
        try:
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
    
    def get_session_thoughts(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[ThoughtLog]:
        """
        Get all thought logs for a specific session
        
        Args:
            session_id: Session identifier
            limit: Optional limit on number of logs
            
        Returns:
            List of thought logs
        """
        try:
            with Session(self.engine) as session_db:
                statement = (
                    select(ThoughtLog)
                    .where(ThoughtLog.session_id == session_id)
                    .order_by(ThoughtLog.created_at.asc())
                )
                
                if limit:
                    statement = statement.limit(limit)
                
                return session_db.exec(statement).all()
                
        except Exception as e:
            logger.error(f"Error getting session thoughts: {e}")
            return []
    
    def check_requires_human(self, mission_id: str) -> bool:
        """
        Check if a mission requires human intervention
        
        Args:
            mission_id: Mission identifier
            
        Returns:
            True if human intervention is required
        """
        try:
            with Session(self.engine) as session:
                statement = (
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
    
    def generate_consolidated_log(self, mission_id: str) -> str:
        """
        Generate a consolidated log of all attempts for a mission.
        Used when escalating to human for review.
        
        Args:
            mission_id: Mission identifier
            
        Returns:
            Formatted consolidated log
        """
        thoughts = self.get_mission_thoughts(mission_id)
        
        if not thoughts:
            return f"No thought logs found for mission {mission_id}"
        
        log_lines = [
            f"=== Consolidated Log for Mission: {mission_id} ===",
            f"Total Attempts: {len(thoughts)}",
            f"Status: {'ESCALATED TO HUMAN' if thoughts[-1].requires_human else 'IN PROGRESS'}",
            "",
        ]
        
        for i, thought in enumerate(thoughts, 1):
            log_lines.extend([
                f"--- Attempt {i} ({thought.created_at.isoformat()}) ---",
                f"Problem: {thought.problem_description}",
                f"Reasoning: {thought.thought_process}",
                f"Solution: {thought.solution_attempt}",
                f"Result: {'SUCCESS' if thought.success else 'FAILED'}",
            ])
            
            if thought.error_message:
                log_lines.append(f"Error: {thought.error_message}")
            
            if thought.context_data and thought.context_data != "{}":
                try:
                    context = json.loads(thought.context_data)
                    log_lines.append(f"Context: {json.dumps(context, indent=2)}")
                except json.JSONDecodeError:
                    log_lines.append(f"Context: {thought.context_data}")
            
            log_lines.append("")
        
        if thoughts[-1].requires_human:
            log_lines.extend([
                "=== COMMANDER INTERVENTION REQUIRED ===",
                f"Reason: {thoughts[-1].escalation_reason}",
                "",
            ])
        
        return "\n".join(log_lines)
    
    def get_pending_escalations(self) -> List[ThoughtLog]:
        """
        Get all missions that require human intervention
        
        Returns:
            List of thought logs requiring human help
        """
        try:
            with Session(self.engine) as session:
                statement = (
                    select(ThoughtLog)
                    .where(ThoughtLog.requires_human == True)
                    .order_by(ThoughtLog.created_at.desc())
                )
                
                return session.exec(statement).all()
                
        except Exception as e:
            logger.error(f"Error getting pending escalations: {e}")
            return []
    
    def get_recent_thoughts(
        self,
        status: Optional[InteractionStatus] = None,
        limit: int = 50
    ) -> List[ThoughtLog]:
        """
        Get recent thought logs, optionally filtered by status
        
        Args:
            status: Optional filter by interaction status
            limit: Maximum number of logs to return
            
        Returns:
            List of recent thought logs
        """
        try:
            with Session(self.engine) as session:
                statement = select(ThoughtLog).order_by(ThoughtLog.created_at.desc())
                
                if status:
                    statement = statement.where(
                        ThoughtLog.status == (status.value if isinstance(status, InteractionStatus) else status)
                    )
                
                statement = statement.limit(limit)
                
                return session.exec(statement).all()
                
        except Exception as e:
            logger.error(f"Error getting recent thoughts: {e}")
            return []
