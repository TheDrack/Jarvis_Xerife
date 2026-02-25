from app.core.interfaces import NexusComponent
from app.core.nexus import nexus

class HumanIntervention(NexusComponent):
    """
    Setor: Application/Communication
    Responsabilidade: Solicitar entrada/ajuda do comandante quando o sistema falha.
    """
    def __init__(self):
        self.state = nexus.resolve("state_manager", hint_path="domain/services")

    def execute(self, issue: str, context: dict = None):
        print(f"\n[ALERTA JARVIS] Intervenção Necessária: {issue}")
        user_input = input("Comandante, como devo proceder? ")
        
        # Logar a intervenção no estado do sistema
        if self.state:
            self.state.execute("update_mission", {"mission_id": f"Intervention: {issue[:20]}"})
            
        return {"action": user_input, "context": context}
