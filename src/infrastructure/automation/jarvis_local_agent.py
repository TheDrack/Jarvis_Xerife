import os
from app.core.nexus import nexus
from app.core.interfaces import NexusComponent

class JarvisLocalAgent(NexusComponent):
    """
    Setor: Infrastructure/Automation
    Responsabilidade: Orquestrar a execução local recebida via Cloud.
    """
    def __init__(self):
        self.hardware = nexus.resolve("hardware_controller", hint_path="infrastructure/automation")
        self.socket = nexus.resolve("socket_client", hint_path="infrastructure/network")
        self.api_key = os.getenv("API_KEY_LOCAL")

    def execute(self, payload: dict):
        """
        Recebe comandos da Cloud e delega para o hardware.
        """
        command = payload.get("command")
        params = payload.get("params", {})

        if not self.hardware:
            return {"error": "HardwareController não cristalizado"}

        # Delegando a ação real para o componente especializado
        result = self.hardware.execute(command, params)
        
        if self.socket:
            self.socket.execute("send", {"event": "command_result", "data": result})
        
        return result

if __name__ == "__main__":
    # Inicialização direta via Nexus
    agent = nexus.resolve("jarvis_local_agent")
    agent.execute({"command": "screenshot"})
