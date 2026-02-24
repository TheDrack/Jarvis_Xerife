import pyautogui
from app.core.interfaces import NexusComponent

class HardwareController(NexusComponent):
    """
    Setor: Infrastructure/Automation
    Responsabilidade Única: Interação direta com periféricos.
    """
    def __init__(self):
        pyautogui.FAILSAFE = True

    def execute(self, action: str, params: dict = None):
        if action == "screenshot":
            return self.take_screenshot()
        if action == "type":
            return self.type_text(params.get("text", ""))

    def take_screenshot(self):
        # Retorna apenas o dado bruto ou salva em local temporário
        return pyautogui.screenshot()

    def type_text(self, text: str):
        pyautogui.write(text)
        return True
