# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Any, Dict

class NexusComponent(ABC):
    """
    Interface do DNA JARVIS. 
    O 'configure' é opcional. O 'execute' é obrigatório.
    """

    def configure(self, config: Dict[str, Any]) -> None:
        """Implementação padrão vazia (Opcional)."""
        pass

    @abstractmethod
    def execute(self, context: Dict[str, Any] = None) -> Any:
        """
        Executa a lógica principal recebendo o contexto do Pipeline.
        """
        pass
