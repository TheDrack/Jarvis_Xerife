# -*- coding: utf-8 -*-
"""
Nexus helpers: exceptions, CloudMock fallback, circuit-breaker entry and
guarded-instantiation utility.

Imported by nexus.py – not intended for direct use in component code.
"""
import logging
import os
from threading import local as _thread_local
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

# Thread-local re-exported so nexus.py and nexuscomponent.py share the same object
# Thread-local context shared between JarvisNexus (discovery/instantiation) and
# NexusComponent (guarded __init__).  JarvisNexus sets ``nexus_context.resolving = True``
# before calling ``cls()`` so that NexusComponent.__init_subclass__ can detect the
# difference between a Nexus-managed instantiation and a direct ``MyComp()`` call.
nexus_context = _thread_local()


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ImportTimeoutError(Exception):
    """Raised when importlib.import_module exceeds NEXUS_IMPORT_TIMEOUT."""


class InstantiateTimeoutError(Exception):
    """Raised when class instantiation exceeds NEXUS_INSTANTIATE_TIMEOUT."""


class AmbiguousComponentError(Exception):
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
    component is unavailable or times out.  Absorbs any method call gracefully.
    """

    __is_cloud_mock__ = True
    _global_fallback_count: int = 0

    def __init__(self, component_id: str = "unknown") -> None:
        self._component_id = component_id
        self._call_count: int = 0
        self._last_calls: List[Dict[str, Any]] = []
        self._metrics_collector: Optional[Any] = None

    def __getattr__(self, name: str):
        def _noop(*args, **kwargs):
            self._call_count += 1
            CloudMock._global_fallback_count += 1
            count = CloudMock._global_fallback_count
            record: Dict[str, Any] = {"method": name, "args": args, "kwargs": kwargs}
            self._last_calls.append(record)
            if len(self._last_calls) > 10:
                self._last_calls = self._last_calls[-10:]
            logger.warning(
                "☁️ [CloudMock] '%s.%s' chamado no fallback (componente real indisponível).",
                self._component_id,
                name,
            )
            if count % 10 == 0:
                logger.critical(
                    "🚨 [NEXUS] ALERTA DE DEGRADAÇÃO: %d fallbacks ocorridos desde o início.",
                    count,
                )
            if self._metrics_collector is not None:
                try:
                    self._metrics_collector.increment("nexus.fallback_count")
                except Exception:
                    pass
            return None

        return _noop

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.warning(
            "☁️ [CloudMock] execute() chamado para '%s' (componente indisponível).",
            self._component_id,
        )
        if isinstance(context, dict):
            context.setdefault("result", {})
            context["result"] = {"fallback": True, "component": self._component_id}
            return context
        return {"fallback": True, "component": self._component_id}


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
    """Instantiate *cls* with the Nexus context flag set.

    Submitted to the thread-pool executor so that ``nexus_context.resolving``
    is set in the same thread that calls ``cls()``.  NexusComponent subclasses
    read this flag in their guarded ``__init__`` to suppress the
    direct-instantiation warning.
    """
    nexus_context.resolving = True
    try:
        return cls()
    finally:
        nexus_context.resolving = False
