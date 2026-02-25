from app.core.interfaces import NexusComponent
from app.core.nexus import nexus

class CentralOrchestrator(NexusComponent):
    """
    Setor: Domain/Orchestration
    Responsabilidade: Coordenar múltiplos componentes para concluir uma tarefa.
    """
    def execute(self, instruction: str):
        # 1. Usa a IA para entender a instrução
        ai_service = nexus.resolve("gemini_service", hint_path="domain/ai")
        plan = ai_service.execute(f"Crie um plano de execução para: {instruction}")

        # 2. Se o plano exigir automação local
        if "screenshot" in plan:
            hardware = nexus.resolve("hardware_controller", hint_path="infrastructure/automation")
            hardware.execute("screenshot")
            
        return {"status": "Mission Accomplished", "plan": plan}
