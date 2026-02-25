from app.core.nexuscomponent import NexusComponent

import logging
from typing import Dict

class TechnicalAnalysisService(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def distinguish_error(self, error_message: str) -> Dict:
        # Define a lista de erros técnicos conhecidos
        technical_errors = [
            'Erro de sintaxe',
            'Erro de tipo',
            'Erro de execução'
        ]

        # Verifica se o erro é técnico
        if any(technical_error in error_message for technical_error in technical_errors):
            return {'error_type': 'technical', 'description': error_message}
        else:
            return {'error_type': 'conceptual', 'description': error_message}

    def analyze(self, error_message: str) -> Dict:
        try:
            result = self.distinguish_error(error_message)
            return result
        except Exception as e:
            self.logger.error(f'Erro ao analisar o erro: {str(e)}')
            return {'error_type': 'unknown', 'description': str(e)}
