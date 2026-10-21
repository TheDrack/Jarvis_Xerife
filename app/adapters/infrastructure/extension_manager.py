import logging
from abc import ABC, abstractmethod
from typing import List, Any, Dict

# Library modules must not configure the root logger; the application entry
# points (bootstrap_edge.py, scripts/*) own logging configuration.
logger = logging.getLogger("ExtensionManager")

class Extension(ABC):
    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Cada extensão recebe um contexto e pode modificá-lo."""
        pass

class ExtensionManager:
    def __init__(self):
        self.extensions: List[Extension] = []

    def register_extension(self, extension: Extension):
        logger.info(f"🧩 Acoplando extensão: {extension.__class__.__name__}")
        self.extensions.append(extension)

    def execute_extensions(self, initial_context: Dict[str, Any] = None) -> Dict[str, Any]:
        context = initial_context or {}
        for extension in self.extensions:
            name = extension.__class__.__name__
            try:
                logger.info(f"🚀 Iniciando: {name}")
                # A mágica acontece aqui: o contexto flui entre as extensões
                result = extension.execute(context)
                if result:
                    context.update(result)
            except Exception as e:
                # Isolamento de falha: se uma falha, o JARVIS apenas loga e continua
                logger.error(f"💥 Falha na extensão {name}: {e}")
        return context
