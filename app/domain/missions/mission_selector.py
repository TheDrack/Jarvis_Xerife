from app.core.interfaces import NexusComponent
from typing import List, Dict

class MissionSelector(NexusComponent):
    """
    Setor: Domain/Missions
    Responsabilidade: Filtrar e ordenar missões por prioridade e impacto.
    """
    def __init__(self):
        self.priority_threshold = 0.7

    def execute(self, missions: List[Dict], criteria: str = "impact") -> List[Dict]:
        """Interface Nexus para decidir o próximo passo."""
        if criteria == "impact":
            return self._sort_by_impact(missions)
        return sorted(missions, key=lambda x: x.get("name", ""))

    def _sort_by_impact(self, missions: List[Dict]):
        # Ordena do maior impacto para o menor
        return sorted(missions, key=lambda x: x.get("impact", 0), reverse=True)
