# -*- coding: utf-8 -*-
"""
Nexus helpers: exceptions, CloudMock fallback, circuit-breaker entry and
guarded-instantiation utility.
Imported by nexus.py – not intended for direct use in component code.
"""
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable timeouts (shared with nexus.py via env vars)
# ---------------------------------------------------------------------------
CIRCUIT_BREAKER_TIMEOUT = float(os.getenv("NEXUS_TIMEOUT", "30.0"))
CIRCUIT_BREAKER_RESET = float(os.getenv("NEXUS_CIRCUIT_RESET", "60.0"))
NEXUS_IMPORT_TIMEOUT = float(os.getenv("NEXUS_IMPORT_TIMEOUT", "10.0"))
NEXUS_INSTANTIATE_TIMEOUT = float(os.getenv("NEXUS_INSTANTIATE_TIMEOUT", "5.0"))
NEXUS_STRICT_MODE = os.getenv("NEXUS_STRICT_MODE", "false").lower() == "true"

# Extra margin added to CIRCUIT_BREAKER_TIMEOUT when a waiter thread blocks
WAITER_TIMEOUT_MARGIN = 1.0

# Thread-local context shared between JarvisNexus and NexusComponent.
# Usamos threading.local() diretamente para garantir isolamento por thread.
nexus_context = threading.local()

def _ensure_context():
    """Garante que os atributos do thread_local existam para evitar AttributeError."""
    if not hasattr(nexus_context, 'resolving'):
        nexus_context.resolving = False

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class NexusError(Exception):
    """Base exception for all Nexus-related errors."""

class ImportTimeoutError(NexusError):
    """Raised when importlib.import_module exceeds NEXUS_IMPORT_TIMEOUT."""

class InstantiateTimeoutError(NexusError):
    """Raised when class instantiation exceeds NEXUS_INSTANTIATE_TIMEOUT."""

class AmbiguousComponentError(NexusError):
    """Raised when >1 filesystem candidate matches the same component_id."""
    def __init__(self, component_id: str, candidates: List[str]) -> None:
        self.component_id = component_id
        self.candidates = candidates
        super().__init__(
            f"Ambiguous component '{component_id}': "
            f"{len(candidates)} candidates found: {candidates}"
        )

# ---------------------------------------------------------------------------
# CloudMock – graceful fallback when a real component is unavailable
# ---------------------------------------------------------------------------
class CloudMock:
    """
    Fallback component injected by the Nexus Circuit Breaker when a real
    component is unavailable or times out. Absorbs any method call gracefully.
    """
    __is_cloud_mock__ = True
    _global_fallback_lock = threading.Lock()
    _global_fallback_count: int = 0

    def __init__(self, component_id: str = "unknown") -> None:
        self._component_id = component_id
        self._call_count: int = 0
        self._last_calls: List[Dict[str, Any]] = []
        self._metrics_collector: Optional[Any] = None

    def __getattr__(self, name: str):
        """Captura chamadas a métodos inexistentes e retorna um no-op funcional."""
        def _noop(*args, **kwargs):
            self._call_count += 1
            
            with CloudMock._global_fallback_lock:
                CloudMock._global_fallback_count += 1
                total_count = CloudMock._global_fallback_count
            
            record: Dict[str, Any] = {"method": name, "args": args, "kwargs": kwargs}
            self._last_calls.append(record)
            if len(self._last_calls) > 10:
                self._last_calls.pop(0)
            
            logger.warning(
                "☁️ [CloudMock] '%s.%s' chamado no fallback (componente real indisponível).",
                self._component_id,
                name,
            )
            
            if total_count % 10 == 0:
                logger.critical(
                    "🚨 [NEXUS] ALERTA DE DEGRADAÇÃO: %d fallbacks ocorridos desde o início.",
                    total_count,
                )
            
            if self._metrics_collector is not None:
                try:
                    self._metrics_collector.increment("nexus.fallback_count", tags={"id": self._component_id})
                except Exception:
                    pass
            
            return None
        
        return _noop

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Implementação explícita do método execute para garantir compatibilidade de contrato."""
        logger.warning(
            "☁️ [CloudMock] execute() chamado para '%s' (componente indisponível).",
            self._component_id,
        )
        res = {"fallback": True, "component": self._component_id, "status": "degraded"}
        if isinstance(context, dict):
            context["result"] = res
            return context
        return res

    def is_available(self) -> bool:
        """Sempre retorna False para indicar que é um mock de falha."""
        return False

# ---------------------------------------------------------------------------
# Internal circuit-breaker state
# ---------------------------------------------------------------------------
class _CircuitBreakerEntry:
    """Internal state for one component inside the circuit breaker."""
    __slots__ = ("open_at", "last_failure")

    def __init__(self) -> None:
        self.open_at: float = 0.0
        self.last_failure: str = ""

# ---------------------------------------------------------------------------
# Nexus-guarded instantiation helper
# ---------------------------------------------------------------------------
def nexus_guarded_instantiate(cls: type) -> Any:
    """
    Instantiate *cls* with the Nexus context flag set.
    Garante que o componente saiba que está sendo instanciado pelo Nexus
    e não manualmente, evitando warnings de inicialização.
    """
    _ensure_context()
    nexus_context.resolving = True
    try:
        # Tenta instanciar a classe. Se a classe exigir argumentos no __init__,
        # este helper assume que o Nexus lida com classes de construtor padrão.
        return cls()
    except Exception as e:
        logger.error("❌ [Nexus] Erro crítico ao instanciar componente %s: %s", cls.__name__, e)
        raise InstantiateTimeoutError(f"Falha na instanciação de {cls.__name__}: {str(e)}")
    finally:
        nexus_context.resolving = False

def is_nexus_resolving() -> bool:
    """Utility para componentes checarem o estado do context local."""
    _ensure_context()
    return getattr(nexus_context, 'resolving', False)
