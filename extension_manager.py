from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class AutomationExtension(ABC):
    """Classe base para todas as extensões do JARVIS"""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def execute(self, context: dict):
        pass

class ExtensionManager:
    """Gerencia o ciclo de vida de extensões complexas"""
    def __init__(self):
        self._extensions = {}

    def register_extension(self, extension: AutomationExtension):
        self._extensions[extension.name] = extension
        logger.info(f"🧩 Extensão '{extension.name}' registrada com sucesso.")

    def run_extension(self, name: str, context: dict):
        ext = self._extensions.get(name)
        if not ext:
            logger.error(f"❌ Extensão '{name}' não encontrada.")
            return None
        
        try:
            logger.info(f"🚀 Executando extensão: {name}")
            return ext.execute(context)
        except Exception as e:
            logger.error(f"💥 Erro ao executar {name}: {e}")
            raise
