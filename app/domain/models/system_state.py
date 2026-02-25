# --- CÓDIGO COMPLETO REESTRUTURADO ---
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class SystemStatus(BaseModel):
    """
    Setor: Domain/Models
    Responsabilidade: Definição estrutural do estado do Jarvis.
    """
    is_active: bool = True
    current_mission: Optional[str] = None
    metabolic_rate: float = Field(default=1.0, description="Nível de carga do sistema")
    resources: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = False # Permite mutabilidade controlada pelo StateManager
