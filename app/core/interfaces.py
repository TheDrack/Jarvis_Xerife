# app/core/interfaces.py
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

    @abstractmethod
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


# Alias de compatibilidade (caso algum loader antigo use esse nome)
Interfaces = NexusComponent