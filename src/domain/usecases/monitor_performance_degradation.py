from app.core.interfaces import NexusComponent
from app.core.nexus import nexus

class MonitorPerformanceDegradation(NexusComponent):
    """
    Setor: Domain/UseCases
    Responsabilidade: Coordenar o fluxo de monitoramento de performance.
    """
    def __init__(self):
        self.analyzer = nexus.resolve("performance_analyzer", hint_path="domain/analysis")
        self.storage = nexus.resolve("reward_logger", hint_path="infrastructure/storage")

    def execute(self, data_frame=None):
        if data_frame is None or data_frame.empty:
            return {"status": "error", "message": "Sem dados para análise"}

        # Delegando a matemática para o Analyzer
        importances = self.analyzer.execute(data_frame)
        
        # Salvando o resultado via Storage
        self.storage.execute("log_reward", {"type": "performance_analysis", "result": importances.tolist()})

        return {"status": "success", "feature_importances": importances}
