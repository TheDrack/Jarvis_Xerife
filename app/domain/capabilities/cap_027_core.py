# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent

class Cap027(NexusComponent):
    """Capacidade: Maintain short-term operational memory"""

    def execute(self, context=None):
        # Validação de Estado Observável
        has_memory = context is not None and 'execution_history' in context

        result = {
            'status': 'active' if has_memory else 'error',
            'id': 'CAP-027'
        }

        # Usa o helper da classe pai para distinguir execução de efeito
        return self.wrap_uncertainty(result, evidence_found=has_memory)
