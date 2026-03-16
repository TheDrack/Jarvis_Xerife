# -*- coding: utf-8 -*-
"""ThoughtLog SQLModel — Armazena raciocínios internos do JARVIS.
Versão 2026.03: Revisada para integridade de tipos e validação de Enums.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel
from enum import Enum


class InteractionStatus(str, Enum):
    """Status da interação para categorização de logs."""
    USER_INTERACTION = "user_interaction"
    INTERNAL_MONOLOGUE = "internal_monologue"


class ThoughtLog(SQLModel, table=True):
    """
    ThoughtLog — Armazena raciocínios internos e ciclos de auto-cura.
    
    Campos técnicos para auditoria de evolução e rewards.
    """
    __tablename__ = "thought_logs"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: str = Field(nullable=False, index=True)
    session_id: str = Field(nullable=False, index=True)
    
    # Uso do tipo Enum para validação automática
    status: InteractionStatus = Field(
        default=InteractionStatus.INTERNAL_MONOLOGUE,
        index=True
    )
    
    thought_process: str = Field(nullable=False)
    problem_description: str = Field(default="")
    solution_attempt: str = Field(default="")
    
    success: bool = Field(default=False, index=True)
    error_message: str = Field(default="")
    retry_count: int = Field(default=0, index=True)
    
    requires_human: bool = Field(default=False, index=True)
    escalation_reason: str = Field(default="")
    
    # Armazenamento de objetos complexos como Strings JSON
    context_data: str = Field(default="{}")
    system_state: str = Field(default="{}")
    discarded_alternatives: str = Field(default="[]")
    
    expected_result: str = Field(default="")
    actual_result: str = Field(default="")
    
    # Métricas vindas do RewardSignalProvider
    reward_received: float = Field(default=0.0)
    reward_value: float = Field(default=0.0)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )

    class Config:
        """Configuração para permitir tipos arbitrários se necessário."""
        arbitrary_types_allowed = True
