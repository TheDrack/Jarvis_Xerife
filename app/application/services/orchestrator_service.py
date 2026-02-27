import threading
from app.core.nexus import NexusComponent

class JARVISOrchestrator(NexusComponent):
    def configure(self, nexus_instance):
        self.nexus = nexus_instance

    def execute(self, context: dict):
        # 1. Roteamento (Sempre executa primeiro)
        router = self.nexus.get_component("cognitive_router")
        context = router.execute(context)

        # 2. Execução de Automação (Soldado) em background se necessário
        if context["metadata"].get("trigger_automation"):
            soldado = self.nexus.get_component("system_executor")
            # Disparo não bloqueante
            threading.Thread(target=soldado.execute, args=(context,)).start()
            context["artifacts"]["final_speech"] = "Comando de automação enviado ao Soldado. Já estou processando."
        else:
            # 3. Execução de LLM (Marcha correta)
            engine = self.nexus.get_component("llm_engine")
            context = engine.execute(context)
            context["artifacts"]["final_speech"] = context["artifacts"].get("llm_response")

        return context
