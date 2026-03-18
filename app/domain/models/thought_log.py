# -*- coding: utf-8 -*-
"""ThoughtLog SQLModel — Armazena raciocínios internos do JARVIS."""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel
from enum import Enum


class InteractionStatus(str, Enum):
    """Status da interação."""
    USER_INTERACTION = "user_interaction"
    INTERNAL_MONOLOGUE = "internal_monologue"


class ThoughtLog(SQLModel, table=True):
    """
    ThoughtLog — Armazena raciocínios internos e ciclos de auto-cura.
    
    Campos:
    - mission_id: Identificador único da missão
    - session_id: Sessão para agrupamento
    - status: USER_INTERACTION ou INTERNAL_MONOLOGUE
    - thought_process: Raciocínio técnico interno
    - problem_description: Problema sendo resolvido
    - solution_attempt: Solução tentada
    - success: Se a tentativa funcionou
    - error_message: Erro se falhou
    - retry_count: Número de tentativas para esta missão
    - requires_human: Se precisa de intervenção humana
    - escalation_reason: Motivo do escalonamento
    - context_ JSON com logs, stack traces, etc.
    - system_state: Snapshot do sistema no momento
    - discarded_alternatives: Alternativas descartadas
    - expected_result: O que se esperava
    - actual_result: O que realmente aconteceu
    - reward_received: Valor do RewardSignalProvider
    """
    __tablename__ = "thought_logs"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: str = Field(nullable=False, index=True)
    session_id: str = Field(nullable=False, index=True)
    status: str = Field(default=InteractionStatus.INTERNAL_MONOLOGUE.value)
    thought_process: str = Field(nullable=False)
    problem_description: str = Field(default="")
    solution_attempt: str = Field(default="")
    success: bool = Field(default=False, index=True)
    error_message: str = Field(default="")
    retry_count: int = Field(default=0, index=True)
    requires_human: bool = Field(default=False, index=True)
    escalation_reason: str = Field(default="")
    context_data str = Field(default="{}")
    system_state: str = Field(default="{}")
    discarded_alternatives: str = Field(default="[]")
    expected_result: str = Field(default="")
    actual_result: str = Field(default="")
    reward_received: float = Field(default=0.0)
    reward_value: float = Field(default=0.0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at: Optional[datetime] = Field(default=None)