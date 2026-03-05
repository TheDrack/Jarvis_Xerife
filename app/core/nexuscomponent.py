# -*- coding: utf-8 -*-
import functools
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

# Shared thread-local so NexusComponent and JarvisNexus observe the same flag.
from app.core.nexus_exceptions import nexus_context as _nexus_context  # noqa: F401

_nexus_component_logger = logging.getLogger(__name__)


def _class_to_component_id(class_name: str) -> str:
    """Convert PascalCase class name to snake_case component_id.

    Examples:
        AuditLogger  -> audit_logger
        LLMService   -> llm_service
        MyClass      -> my_class
    """
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", class_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


class NexusComponent(ABC):
    """
    Interface do DNA JARVIS.
    Implementa o princípio de Validação Baseada em Evidência.
    """

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Instrument every concrete subclass to warn on direct instantiation.

        Each subclass that defines its own ``__init__`` gets a guarded wrapper
        that emits a warning when the component is created without going through
        ``nexus.resolve``.  The warning is purely advisory – it never blocks
        execution – and is designed to let Jarvis detect and self-correct
        improper usage patterns.
        """
        super().__init_subclass__(**kwargs)

        original_init = cls.__dict__.get("__init__")
        if original_init is None:
            return

        @functools.wraps(original_init)
        def _guarded_init(self: Any, *args: Any, **kw: Any) -> None:
            if not getattr(_nexus_context, "resolving", False):
                _nexus_component_logger.warning(
                    "⚠️ [NEXUS] '%s' foi instanciado diretamente sem usar nexus.resolve. "
                    "Prefira nexus.resolve('%s') para garantir o gerenciamento correto "
                    "do ciclo de vida pelo Nexus.",
                    type(self).__name__,
                    _class_to_component_id(type(self).__name__),
                )
            original_init(self, *args, **kw)

        cls.__init__ = _guarded_init

    def configure(self, config: Dict[str, Any]) -> None:
        """Configuração opcional antes da execução."""
        pass

    def can_execute(self, context: Dict[str, Any]) -> bool:
        """
        Verifica se este componente pode executar dado o contexto.
        Implementação padrão sempre retorna True.
        Sobrescreva para adicionar pré-condições.
        """
        return True

    @abstractmethod
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retorna obrigatoriamente evidência de efeito."""
        pass

    def wrap_uncertainty(self, result: Dict[str, Any], evidence_found: bool) -> Dict[str, Any]:
        """Propaga incerteza se o efeito no mundo não for medido."""
        if not evidence_found:
            result["execution_state"] = "uncertain"
            result["evidence_missing"] = True
            # Tratamos ausência de evidência como falha operacional
            result["success"] = False
        else:
            result["execution_state"] = "confirmed"
            result["success"] = True
        return result
