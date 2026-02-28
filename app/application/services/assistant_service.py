from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class AssistantService(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    def __init__(self, executor, intent_processor, strategist=None):
        self.executor = executor
        self.intent_processor = intent_processor
        self.strategist = strategist
        self.execution_history = []

    def process_command(self, user_input: str) -> Dict[str, Any]:
        """
        Processa comandos garantindo que cada passo possua evidência observável.
        Interrompe a cadeia em caso de incerteza ou falha de confirmação.
        """
        # 1. Identificação de Intenção
        intent = self.intent_processor.process(user_input)
        if not intent or not hasattr(intent, 'actions'):
            return {
                "success": False, 
                "error": "Não foi possível decompor o comando em ações claras.",
                "execution_state": "failed"
            }

        final_results = []
        
        # 2. Execução Sequencial com Validação de Efeito
        for action in intent.actions:
            # Antes de executar a próxima, verifica se o sistema está em estado íntegro
            if final_results and not final_results[-1].get('success'):
                error_msg = f"Cadeia interrompida. Ação anterior ({final_results[-1].get('action')}) não confirmou efeito."
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "partial_results": final_results,
                    "execution_state": "broken_chain"
                }

            # Execução da Ação
            try:
                result = self.executor.execute(action)
            except Exception as e:
                result = {
                    "action": action,
                    "success": False,
                    "error": str(e),
                    "execution_state": "exception"
                }

            # 3. Verificação de Evidência (Obrigatória)
            # Se o adaptador não retornar 'execution_state', tratamos como incerto por omissão
            exec_state = result.get('execution_state', 'uncertain')
            
            if exec_state == 'uncertain':
                # Marcamos explicitamente como falha técnica por falta de evidência
                result['success'] = False
                result['error'] = "Execução realizada, mas efeito no mundo não pôde ser confirmado (Ausência de Evidência)."
            
            final_results.append(result)
            self.execution_history.append(result)

            # Se falhou ou é incerto, paramos aqui
            if not result['success']:
                break

        # 4. Consolidação do Resultado Final
        overall_success = all(r.get('success', False) for r in final_results)
        
        return {
            "input": user_input,
            "success": overall_success,
            "actions_executed": len(final_results),
            "details": final_results,
            "execution_state": "confirmed" if overall_success else "failed_or_uncertain"
        }

    def get_last_confirmed_state(self) -> Optional[Dict[str, Any]]:
        """Retorna apenas a última ação que teve sucesso confirmado."""
        for res in reversed(self.execution_history):
            if res.get('execution_state') == 'confirmed':
                return res
        return None
