# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class NexusComponent(ABC):
    """
    Interface do DNA JARVIS.
    Implementa o princípio de Validação Baseada em Evidência.
    """
    def configure(self, config: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna obrigatoriamente evidência de efeito."""
        pass

    def wrap_uncertainty(self, result: Dict[str, Any], evidence_found: bool) -> Dict[str, Any]:
        """Propaga incerteza se o efeito no mundo não for medido."""
        if not evidence_found:
            result['execution_state'] = 'uncertain'
            result['evidence_missing'] = True
            # Tratamos ausência de evidência como falha operacional
            result['success'] = False 
        else:
            result['execution_state'] = 'confirmed'
            result['success'] = True
        return result
