# --- CÓDIGO COMPLETO REESTRUTURADO ---
from app.core.interfaces import NexusComponent
from app.core.nexus import nexus

class MonitorPerformanceDegradation(NexusComponent):
    """
    Setor: Domain/UseCases
    Responsabilidade: Orquestrar a análise de saúde do sistema.
    """
    def __init__(self):
        self.analyzer = nexus.resolve("performance_analyzer")
        self.logger = nexus.resolve("reward_logger")

    def execute(self, metrics_data: any):
        """Fluxo: Analisar -> Logar -> Reportar"""
        if not self.analyzer:
            return "Analisador não encontrado no Nexus."

        # A matemática pesada acontece no setor Domain/Analysis
        analysis_result = self.analyzer.execute(metrics_data)
        
        # O registo acontece no setor Infrastructure/Storage
        self.logger.execute("log_reward", {"metrics": analysis_result})
        
        return analysis_result
