# -*- coding: utf-8 -*-
"""
Nexus Component Base: The DNA of the JARVIS environment.
Implements the execution guard, self-healing triggers, and global shielding.
"""
import functools
import logging
import re
import sys
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

# Importação protegida para evitar erros de importação circular
try:
    from app.core.nexus_exceptions import nexus_context as _nexus_context
except ImportError:
    # Fallback caso o módulo de exceções ainda não esteja carregado
    import threading
    _nexus_context = threading.local()
    _nexus_context.resolving = False

_nexus_component_logger = logging.getLogger(__name__)

def _class_to_component_id(class_name: str) -> str:
    """Converte PascalCase para snake_case (Ex: LocalRepairAgent -> local_repair_agent)."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", class_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()

class NexusComponent(ABC):
    """
    Interface fundamental do DNA JARVIS.
    Implementa a Blindagem Global via metaprogramação no __init_subclass__.
    """
    
    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        
        # 1. Guardião de Instanciação
        # Intercepta o __init__ para garantir que o componente foi criado via Nexus
        original_init = cls.__init__
        
        @functools.wraps(original_init)
        def _guarded_init(self: Any, *args: Any, **kw: Any) -> None:
            if not getattr(_nexus_context, "resolving", False):
                _nexus_component_logger.warning(
                    "⚠️ [NEXUS] '%s' instanciado diretamente. "
                    "Recomendado usar nexus.resolve('%s').",
                    type(self).__name__,
                    _class_to_component_id(type(self).__name__),
                )
            original_init(self, *args, **kw)
        
        cls.__init__ = _guarded_init
        
        # 2. Guardião de Execução + Auto-Cura
        # Intercepta o método execute() para capturar falhas em tempo de execução
        original_execute = cls.execute

        @functools.wraps(original_execute)
        def _guarded_execute(self, context: Optional[Dict[str, Any]] = None, **kw: Any) -> Dict[str, Any]:
            try:
                # Garante que context seja ao menos um dict vazio
                if context is None:
                    context = {}
                
                # Executa a lógica real do componente
                return original_execute(self, context, **kw)
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                error_tb = traceback.format_exc()
                
                _nexus_component_logger.error(
                    f"💥 [NEXUS GUARD] Erro em {cls.__name__}: {error_type} - {error_msg}"
                )
                
                # Prevenção de loop infinito: Componentes de cura não curam a si mesmos
                anti_loop = {
                    "LocalRepairAgent", 
                    "FieldVision", 
                    "EvolutionOrchestrator", 
                    "SelfHealingTriggerService",
                    "JarvisDevAgent"
                }
                
                if cls.__name__ not in anti_loop:
                    _nexus_component_logger.info(f"🧬 [NEXUS GUARD] Iniciando protocolo de auto-cura para {cls.__name__}...")
                    try:
                        from app.core.nexus import nexus
                        
                        # Extrai o caminho do arquivo para facilitar o reparo pelo agente
                        file_path = None
                        module = sys.modules.get(self.__module__)
                        if module and hasattr(module, '__file__'):
                            file_path = module.__file__
                        
                        # Tenta resolver o agente de reparo local
                        local_agent = nexus.resolve("local_repair_agent")
                        
                        # Verifica se o agente é válido e não é um fallback (CloudMock)
                        if local_agent and not getattr(local_agent, "__is_cloud_mock__", False):
                            repair_ctx = {
                                "error_type": error_type,
                                "error_message": error_msg,
                                "traceback": error_tb,
                                "file_path": file_path,
                                "component": cls.__name__,
                                "timestamp": getattr(self, "last_execution", None)
                            }
                            
                            repair_result = local_agent.execute(repair_ctx)
                            
                            if repair_result and repair_result.get("fixed"):
                                _nexus_component_logger.info(f"✅ [NEXUS GUARD] Componente {cls.__name__} reparado com sucesso!")
                            elif repair_result and repair_result.get("escalate_to_ci"):
                                _nexus_component_logger.warning(f"⚠️ [NEXUS GUARD] Reparo local falhou. Escalado para CI/Dev.")
                                
                    except Exception as healing_err:
                        _nexus_component_logger.error(f"❌ [NEXUS GUARD] Falha crítica no motor de cura: {healing_err}")
                
                # Retorno estruturado (Fail-Safe) para evitar que o erro derrube o sistema inteiro
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": error_type,
                    "traceback": error_tb,
                    "component": cls.__name__,
                    "nexus_guarded": True,
                    "recovery_status": "attempted" if cls.__name__ not in anti_loop else "skipped"
                }
        
        cls.execute = _guarded_execute

    def configure(self, config: Dict[str, Any]) -> None:
        """Configuração opcional de runtime. Pode ser sobrescrito."""
        pass

    def can_execute(self, context: Dict[str, Any]) -> bool:
        """Verificação de pré-condições. Pode ser sobrescrito."""
        return True

    @abstractmethod
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Contrato obrigatório de execução de todos os componentes Nexus."""
        pass

    def wrap_uncertainty(self, result: Dict[str, Any], evidence_found: bool) -> Dict[str, Any]:
        """Gerencia o estado de confirmação de resultados ambíguos."""
        if not evidence_found:
            result["execution_state"] = "uncertain"
            result["success"] = False
        else:
            result["execution_state"] = "confirmed"
            result["success"] = True
        return result
