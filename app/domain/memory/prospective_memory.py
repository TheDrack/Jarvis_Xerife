# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import uuid

class ProspectiveMemory(BaseModel):
    """
    Representa uma intenção ou tarefa futura que o sistema precisa monitorar (Memória Prospectiva).
    Essencial para o ciclo de auto-evolução do JARVIS.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID único da memória")
    intent: str = Field(..., description="Descrição da intenção ou objetivo futuro")
    priority: int = Field(default=3, ge=1, le=5)
    
    # CORREÇÃO: Sintaxe de atribuição de tipo corrigida (de 'known_ Dict' para 'known_data:')
    known_data: Dict[str, Any] = Field(default_factory=dict, description="Dados já coletados para esta intenção")
    
    # CORREÇÃO: Nome da variável definido (de 'resolved_ Optional' para 'resolved_data:')
    missing_data: List[str] = Field(default_factory=list, description="Dados que ainda precisam ser obtidos")
    resolved_data: Optional[str] = Field(default=None, description="Resultado final após a conclusão")
    
    status: str = Field(default="pending", description="Status: pending, in_progress, completed, failed")
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Verifica se o prazo para cumprir a intenção expirou."""
        if not self.expires_at:
            return False
        return datetime.now() > self.expires_at

    def update_progress(self, data: Dict[str, Any]):
        """Atualiza a memória com novos dados descobertos."""
        self.known_data.update(data)
        # Remove dos dados faltantes o que foi encontrado
        self.missing_data = [item for item in self.missing_data if item not in data]
        if not self.missing_data:
            self.status = "completed"
