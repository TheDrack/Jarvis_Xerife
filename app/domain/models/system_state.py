from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class SystemStatus(BaseModel):
    """Apenas a definição do que é o estado do sistema."""
    is_active: bool = True
    current_mission: Optional[str] = None
    resources: Dict[str, Any] = Field(default_factory=dict)
    metabolic_rate: float = 1.0

# Nexus Compatibility
SystemState = SystemStatus
