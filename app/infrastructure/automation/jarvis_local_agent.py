import os
from app.core.nexus import nexus
from app.core.interfaces import NexusComponent

class JarvisLocalAgent(NexusComponent):
    """
    Setor: Infrastructure/Automation
    Responsabilidade: Execução local.
    """
    def __init__(self):
        # Ele não importa o código, ele pede ao Nexus
        self.hardware = nexus.resolve("hardware_controller")
        self.network = nexus.resolve("socket_client")

    def execute(self, command_data: dict):
        # Toda a lógica suja de pyautogui saiu daqui e foi para o hardware_controller
        action = command_data.get("action")
        return self.hardware.execute(action)

