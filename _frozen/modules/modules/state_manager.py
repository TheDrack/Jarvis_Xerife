from app.core.interfaces import NexusComponent
from app.domain.models.system_state import SystemStatus

class StateManager(NexusComponent):
    """
    Setor: Domain/Services
    Responsabilidade: Controlar as transições de estado do Jarvis.
    """
    def __init__(self):
        self._state = SystemStatus()

    def execute(self, action: str, data: dict = None):
        """Interface única do Nexus para gerir o estado."""
        if action == "update_mission":
            return self._set_mission(data.get("mission_id"))
        if action == "get_status":
            return self._state.model_dump()
        return {"error": "Ação de estado desconhecida"}

    def _set_mission(self, mission_id: str):
        self._state.current_mission = mission_id
        return {"status": "updated", "mission": mission_id}
