import pyautogui
import keyboard
import webbrowser
from app.core.nexus import NexusComponent

class SystemExecutor(NexusComponent):
    def configure(self, config=None):
        pyautogui.PAUSE = 0.5
        pyautogui.FAILSAFE = True

    def can_execute(self, context: dict):
        return context["metadata"].get("trigger_automation") is True

    def execute(self, context: dict):
        cmd = context["metadata"]["user_input"].lower()
        
        if "tirar foto" in cmd or "print" in cmd:
            pyautogui.screenshot("screenshot.png")
            context["artifacts"]["automation_log"] = "Screenshot capturada."
        
        elif "digite" in cmd:
            texto = cmd.replace("digite", "").strip()
            pyautogui.write(texto)
            context["artifacts"]["automation_log"] = f"Texto '{texto}' digitado."
            
        elif "abra o navegador" in cmd or "pesquise" in cmd:
            url = "https://www.google.com"
            webbrowser.open(url)
            context["artifacts"]["automation_log"] = "Navegador aberto."

        return context
