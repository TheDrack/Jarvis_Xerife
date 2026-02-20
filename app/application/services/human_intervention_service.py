
import logging

class HumanInterventionService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def request_human_intervention(self, task_id, reason):
        # Verificar se a intervenção humana é necessária com base na razão
        if reason == 'unknown_error':
            self.logger.warning(f'Tarefa {task_id} requer intervenção humana devido a um erro desconhecido')
            # Implementar lógica para solicitar intervenção humana
            return True
        elif reason == 'validation_error':
            self.logger.info(f'Tarefa {task_id} requer intervenção humana devido a um erro de validação')
            # Implementar lógica para solicitar intervenção humana
            return True
        else:
            self.logger.info(f'Tarefa {task_id} não requer intervenção humana')
            return False
   