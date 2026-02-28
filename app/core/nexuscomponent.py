#app.core.nexuscomponent.py
from abc import ABC, abstractmethod
from typing import Any, Dict


class NexusComponent(ABC):
    """
    Interface obrigatória para componentes descobertos pelo Jarvis Nexus.

    Todo componente:
    - é instanciado pelo Nexus
    - recebe configuração via configure()
    - executa sua função principal via execute()
    """

    def configure(self, config: Dict[str, Any]) -> None:
        """
        Recebe configuração declarada no pipeline.yml.
        Deve preparar o estado interno do componente.
        """
        pass

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """
        Executa a lógica principal do componente.
        """
        pass