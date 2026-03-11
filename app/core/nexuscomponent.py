# -*- coding: utf-8 -*-
import functools
import logging
import re
import sys
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.core.nexus_exceptions import nexus_context as _nexus_context

_nexus_component_logger = logging.getLogger(__name__)


def _class_to_component_id(class_name: str) -> str:
    """Convert PascalCase → snake_case."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", class_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


class NexusComponent(ABC):
    """
    Interface do DNA JARVIS.
    COM GUARDIÃO GLOBAL + AUTO-CURA EMBUTIDA.
    """

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # 1. Guardião de Instanciação
        original_init = cls.__dict__.get("__init__")
        if original_init is not None:
            @functools.wraps(original_init)
            def _guarded_init(self: Any, *args: Any, **kw: Any) -> None:
                if not getattr(_nexus_context, "resolving", False):
                    _nexus_component_logger.warning(
                        "⚠️ [NEXUS] '%s' instanciado diretamente. "
                        "Prefira nexus.resolve('%s').",
                        type(self).__name__,
                        _class_to_component_id(type(self).__name__),
                    )
                original_init(self, *args, **kw)
            cls.__init__ = _guarded_init

        # 2. Guardião de Execução + Auto-Cura
        original_execute = cls.__dict__.get("execute")
        if original_execute is not None:
            @functools.wraps(original_execute)
            def _guarded_execute(self, context: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:                try:
                    return original_execute(self, context, **kw)
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    error_tb = traceback.format_exc()
                    
                    _nexus_component_logger.error(
                        f"💥 [NEXUS GUARD] {cls.__name__}: {error_type} - {error_msg}"
                    )

                    # Anti-loop: componentes de cura não se auto-curam
                    anti_loop = {"LocalRepairAgent", "FieldVision", "EvolutionOrchestrator", 
                                 "SelfHealingTriggerService", "JarvisDevAgent"}
                    
                    if cls.__name__ not in anti_loop:
                        _nexus_component_logger.info(f"🧬 [NEXUS GUARD] Trigger self-healing para {cls.__name__}...")
                        try:
                            from app.core.nexus import nexus
                            
                            # Descobre arquivo físico automaticamente (Gemini)
                            file_path = None
                            module = sys.modules.get(cls.__module__)
                            if module and hasattr(module, '__file__'):
                                file_path = module.__file__

                            local_agent = nexus.resolve("local_repair_agent")
                            if local_agent and not getattr(local_agent, "__is_cloud_mock__", False):
                                repair_ctx = {
                                    "error_type": error_type,
                                    "error_message": error_msg,
                                    "traceback": error_tb,
                                    "file_path": file_path,
                                    "component": cls.__name__,
                                }
                                repair_result = local_agent.execute(repair_ctx)
                                
                                if repair_result and repair_result.get("fixed"):
                                    _nexus_component_logger.info(f"✅ [NEXUS GUARD] {cls.__name__} curado localmente!")
                                elif repair_result and repair_result.get("escalate_to_ci"):
                                    _nexus_component_logger.warning(f"⚠️ [NEXUS GUARD] {cls.__name__} escalado para CI.")
                        except Exception as healing_err:
                            _nexus_component_logger.error(f"❌ [NEXUS GUARD] Falha no self-healing: {healing_err}")

                    # Retorno rico em informações (minha solução)
                    return {
                        "success": False,
                        "error": error_msg,
                        "error_type": error_type,
                        "traceback": error_tb,                        "component": cls.__name__,
                        "nexus_guarded": True,
                    }

            cls.execute = _guarded_execute

    def configure(self, config: Dict[str, Any]) -> None:
        """Configuração opcional."""
        pass

    def can_execute(self, context: Dict[str, Any]) -> bool:
        """Pré-condições de execução."""
        return True

    @abstractmethod
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna evidência de efeito."""
        pass