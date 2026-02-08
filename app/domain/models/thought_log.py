# -*- coding: utf-8 -*-
"""ThoughtLog model for storing internal reasoning and self-healing cycles"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class InteractionStatus(str, Enum):
    """Status types for interaction modes"""
    
    USER_INTERACTION = "user_interaction"  # Response visible to user
    INTERNAL_MONOLOGUE = "internal_monologue"  # Internal reasoning, not shown to user


class ThoughtLog(SQLModel, table=True):
    """
    SQLModel table for storing Jarvis's internal reasoning process.
    Used for debugging, self-healing, and tracking problem-solving attempts.
    Does not pollute user interface - only visible in admin/debug views.
    """

    __tablename__ = "thought_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: str = Field(nullable=False, index=True)  # Links related thoughts to same mission
    session_id: str = Field(nullable=False, index=True)  # Groups thoughts in same session
    status: str = Field(default=InteractionStatus.INTERNAL_MONOLOGUE.value, nullable=False)  # USER_INTERACTION or INTERNAL_MONOLOGUE
    
    # Reasoning content
    thought_process: str = Field(default="", nullable=False)  # Technical reasoning
    problem_description: str = Field(default="", nullable=False)  # What problem is being solved
    solution_attempt: str = Field(default="", nullable=False)  # What solution was tried
    
    # Execution tracking
    success: bool = Field(default=False, nullable=False)  # Did this attempt succeed
    error_message: str = Field(default="", nullable=False)  # Error if failed
    retry_count: int = Field(default=0, nullable=False)  # Number of retries for this mission
    
    # Metadata
    context_data: str = Field(default="{}", nullable=False)  # JSON string for additional context (logs, stack traces, etc.)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Auto-healing tracking
    requires_human: bool = Field(default=False, nullable=False)  # Escalated to human after 3 failures
    escalation_reason: str = Field(default="", nullable=False)  # Why escalation was needed
