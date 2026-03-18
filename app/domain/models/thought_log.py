# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import uuid

class ThoughtLog(BaseModel):
    """
    Representa um registo de pensamento ou etapa de raciocínio de um Agente.
    Essencial para a observabilidade do ciclo de vida do JARVIS.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único do log")
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = Field(..., description="ID do agente que gerou o pensamento")
    
    # CORREÇÃO: Nome da variável e tipagem (de 'context_ str' para 'context_data: str')
    context_data: str = Field(..., description="O trigger ou contexto que iniciou o pensamento")
    
    thought_process: str = Field(..., description="A cadeia de raciocínio detalhada (Chain of Thought)")
    action_taken: Optional[str] = Field(default=None, description="Ação decidida após o pensamento")
    observation: Optional[str] = Field(default=None, description="Observação após a execução da ação")
    
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Dados técnicos adicionais")

    def to_dict(self) -> Dict[str, Any]:
        """Converte o log para dicionário para persistência."""
        return self.model_dump()

class ThoughtStep(BaseModel):
    """Sub-etapa de um pensamento complexo."""
    step_name: str
    description: str
    status: str = "completed"
