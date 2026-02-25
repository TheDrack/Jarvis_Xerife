import json
from app.core.interfaces import NexusComponent

class RewardLogger(NexusComponent):
    """
    Setor: Infrastructure/Storage
    Responsabilidade: Gravar o histórico de aprendizado do sistema.
    """
    def __init__(self):
        self.log_path = "storage/rewards_history.json"

    def execute(self, action: str, reward_data: dict = None):
        if action == "log_reward":
            return self._save(reward_data)
        return {"status": "idle"}

    def _save(self, data):
        # Lógica de escrita em arquivo (infraestrutura pura)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(data) + "\n")
        return True
