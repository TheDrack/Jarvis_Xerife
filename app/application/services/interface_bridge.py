from app.core.nexus import NexusComponent
import time

class InterfaceBridge(NexusComponent):
    def execute(self, context: dict):
        # Prepara o payload para a interface web
        response_payload = {
            "timestamp": time.time(),
            "display_text": context["artifacts"].get("final_speech"),
            "automation_triggered": context["metadata"].get("trigger_automation", False),
            "marcha_utilizada": context["metadata"].get("marcha"),
            "executor": context["metadata"].get("executor_real", "system"),
            "status": "success" if "last_error" not in context["metadata"] else "warning"
        }

        # No padrão JARVIS, o resultado vai para artifacts para o Runner publicar
        context["artifacts"]["web_response"] = response_payload
        return context
