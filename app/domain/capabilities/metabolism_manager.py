import time
from app.core.nexus import NexusComponent

class MetabolismManager(NexusComponent):
    """
    Componente de Auto-Cura: Monitora falhas e reinicia contratos.
    """
    def configure(self, config={"max_failures": 3}):
        self.max_failures = config["max_failures"]
        self.failure_counter = {}

    def execute(self, context: dict):
        last_error = context["metadata"].get("last_error")
        component_in_error = context["metadata"].get("last_failed_component")

        if last_error and component_in_error:
            self.failure_counter[component_in_error] = self.failure_counter.get(component_in_error, 0) + 1

            print(f"[METABOLISMO]: Detectada falha no componente {component_in_error}. Tentativa {self.failure_counter[component_in_error]}/{self.max_failures}")

            if self.failure_counter[component_in_error] >= self.max_failures:
                print(f"[METABOLISMO]: Resetando componente {component_in_error} via Nexus...")
                # Lógica de auto-cura: limpa o erro e força o componente a se reconfigurar
                self.failure_counter[component_in_error] = 0
                context["metadata"]["last_error"] = None
                context["metadata"]["recovery_triggered"] = True

        return context
