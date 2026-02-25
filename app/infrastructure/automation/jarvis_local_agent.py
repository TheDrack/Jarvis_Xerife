# --- CÓDIGO COMPLETO REESTRUTURADO ---
import os
from app.core.nexus import nexus
from app.core.interfaces import NexusComponent

class JarvisLocalAgent(NexusComponent):
    """
    Setor: Infrastructure/Automation
    Responsabilidade: Ponte de comando entre Cloud e Hardware Local.
    """
    def __init__(self):
        # O Nexus resolve as dependências de hardware e rede
        self.hardware = nexus.resolve("hardware_controller")
        self.network = nexus.resolve("socket_client")
        self.auth_key = os.getenv("API_KEY_LOCAL")

    def execute(self, task_payload: dict):
        """Executa comandos delegados"""
        if not self.hardware:
            return {"status": "error", "reason": "Hardware Controller não disponível"}

        action = task_payload.get("action")
        params = task_payload.get("params", {})

        # Delegação certeira
        result = self.hardware.execute(action, params)
        
        if self.network:
            self.network.execute("emit", {"event": "task_complete", "data": result})
            
        return result
