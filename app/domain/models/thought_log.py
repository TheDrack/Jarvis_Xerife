# -*- coding: utf-8 -*-
"""ThoughtLog SQLModel — Armazena raciocínios internos do JARVIS."""
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
    
    Campos:
    - mission_id: Identificador único da missão (UUID ou Hash)
    - session_id: Agrupamento por sessão de chat
    - status: Tipo de entrada (Interação ou Monólogo Interno)
    - thought_process: Raciocínio técnico/lógico da IA
    - problem_description: Descrição do erro ou desafio
    - success: Booleano indicando se a ação foi bem-sucedida
    - reward_received: Sinal de feedback positivo/negativo para o agente
    """
    __tablename__ = "thought_logs"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    mission_id: str = Field(nullable=False, index=True)
    session_id: str = Field(nullable=False, index=True)
    
    # CORREÇÃO: Tipagem direta com Enum para validação rigorosa do SQLModel/Pydantic
    status: InteractionStatus = Field(
        default=InteractionStatus.INTERNAL_MONOLOGUE,
        nullable=False
    )
    
    thought_process: str = Field(nullable=False)
    problem_description: str = Field(default="")
    solution_attempt: str = Field(default="")
    success: bool = Field(default=False, index=True)
    error_message: str = Field(default="")
    retry_count: int = Field(default=0, index=True)
    requires_human: bool = Field(default=False, index=True)
    escalation_reason: str = Field(default="")
    
    # Dados serializados (JSON strings para compatibilidade SQLite/Postgres)
    context_data: str = Field(default="{}")
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

    class Config:
        """Configurações adicionais de validação."""
        arbitrary_types_allowed = True
