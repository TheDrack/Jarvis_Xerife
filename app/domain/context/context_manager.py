from app.core.interfaces import NexusComponent
import json
import os

class ContextManager(NexusComponent):
    """
    Setor: Domain/Context
    Objetivo: Gerenciar o estado mental e variáveis de ambiente do Jarvis.
    """
    def __init__(self):
        self.state_path = "storage/state.json"
        self.current_context = {}

    def execute(self, action: str, data: dict = None) -> dict:
        """
        Ponto de entrada único exigido pelo Nexus.
        """
        actions = {
            "save": self._save_state,
            "load": self._load_state,
            "update": self._update_context
        }
        
        executor = actions.get(action)
        if executor:
            return executor(data)
        return {"error": "Ação inválida no ContextManager"}

    def _save_state(self, data):
        with open(self.state_path, 'w') as f:
            json.dump(data, f)
        return {"status": "saved"}

    def _load_state(self, _):
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r') as f:
                return json.load(f)
        return {}

    def _update_context(self, data):
        self.current_context.update(data)
        return self.current_context
