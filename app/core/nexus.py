# -*- coding: utf-8 -*-
"""
JarvisNexus – Dynamic Dependency Injection Container.

Environment variables:
    NEXUS_TIMEOUT              Circuit-breaker wall-clock timeout in seconds (default: 2.0)
    NEXUS_CIRCUIT_RESET        Cooling-off period before retrying a tripped circuit (default: 60.0)
    NEXUS_IMPORT_TIMEOUT       Fine-grained import timeout (default: 1.0)
    NEXUS_INSTANTIATE_TIMEOUT  Fine-grained instantiation timeout (default: 1.0)
    NEXUS_STRICT_MODE          Skip filesystem discovery; only use registry (default: false)
    NEXUS_GIST_ID              GitHub Gist ID for remote registry sync
    GIST_PAT                   Personal access token for GitHub Gist PATCH calls

Quick start::

    from app.core.nexus import nexus, NexusComponent

    class MyAdapter(NexusComponent):
        def execute(self, context):
            ...

    instance = nexus.resolve("my_adapter")
    cls      = nexus.resolve_class("my_adapter")  # returns the class without instantiating
"""
import concurrent.futures
import logging
import os
import time
from threading import RLock
from typing import Any, Dict, Optional

from app.core.nexus_exceptions import (
    CIRCUIT_BREAKER_RESET,
    CIRCUIT_BREAKER_TIMEOUT,
    WAITER_TIMEOUT_MARGIN,
    CloudMock,
    _CircuitBreakerEntry,
)
from app.core.nexus_discovery import _NexusDiscoveryMixin
from app.core.nexus_registry import _NexusRegistryMixin

# Re-export NexusComponent so components only need to import from this module
from app.core.nexuscomponent import NexusComponent  # noqa: F401

# Re-export helpers used by external code
from app.core.nexus_exceptions import (  # noqa: F401
    AmbiguousComponentError,
    ImportTimeoutError,
    InstantiateTimeoutError,
    nexus_guarded_instantiate as _nexus_guarded_instantiate,  # backward-compat alias
)

# Backward-compatible constant aliases used by existing tests
from app.core.nexus_exceptions import CIRCUIT_BREAKER_RESET as _CIRCUIT_BREAKER_RESET  # noqa: F401
from app.core.nexus_exceptions import CIRCUIT_BREAKER_TIMEOUT as _CIRCUIT_BREAKER_TIMEOUT  # noqa: F401
from app.core.nexus_exceptions import NEXUS_STRICT_MODE as _NEXUS_STRICT_MODE  # noqa: F401

# Backward-compatible codec aliases – tests patch these at module level
from app.utils.jrvs_codec import read_file as _jrvs_read  # noqa: F401
from app.utils.jrvs_codec import write_file as _jrvs_write  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "JarvisNexus",
    "NexusComponent",
    "CloudMock",
    "AmbiguousComponentError",
    "ImportTimeoutError",
    "InstantiateTimeoutError",
    "nexus",
]


class JarvisNexus(_NexusDiscoveryMixin, _NexusRegistryMixin):
    """Thread-safe DI container with circuit-breaker and filesystem discovery."""

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._cache: Dict[str, str] = {}
        self._mutated: bool = False
        self.dna: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}
        self._circuit_breaker: Dict[str, _CircuitBreakerEntry] = {}
        self._lock: RLock = RLock()
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._metrics_collector: Optional[Any] = None
        self.gist_id: str = os.getenv("NEXUS_GIST_ID", "")
        self.base_dir: str = os.path.abspath(os.getcwd())
        self._cache.update(self._load_local_registry())

    def _get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="nexus"
            )
        return self._executor

    def register_metrics_collector(self, collector: Any) -> None:
        """Register an object with increment(name) and observe(name, value)."""
        self._metrics_collector = collector

    def load_dna(self, dna_dict: dict) -> None:
        self.dna = dna_dict
        for c_id, meta in dna_dict.get("components", {}).items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def _is_circuit_open(self, target_id: str) -> bool:
        entry = self._circuit_breaker.get(target_id)
        if entry is None:
            return False
        if time.monotonic() - entry.open_at < CIRCUIT_BREAKER_RESET:
            return True
        del self._circuit_breaker[target_id]
        return False

    def _open_circuit(self, target_id: str, reason: str) -> None:
        entry = _CircuitBreakerEntry()
        entry.open_at = time.monotonic()
        entry.last_failure = reason
        self._circuit_breaker[target_id] = entry
        logger.error(
            "⚡ [NEXUS] Circuit Breaker ABERTO para '%s': %s. Injetando CloudMock por %.0fs.",
            target_id, reason, CIRCUIT_BREAKER_RESET,
        )

    def invalidate_component(self, component_id: str) -> None:
        """Remove *component_id* from the path-cache and instance cache.

        Called by components (e.g. CrystallizerEngine) after writing a new
        file to disk so that the next ``resolve()`` discovers the fresh module.
        """
        with self._lock:
            if component_id in self._cache:
                del self._cache[component_id]
            if component_id in self._instances:
                del self._instances[component_id]
        self._mutated = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_loaded_ids(self) -> list:
        """Return a copy of the IDs of all currently loaded component instances.

        Thread-safe: acquires the internal lock before reading ``_instances``.

        Returns:
            A new list of component ID strings.
        """
        with self._lock:
            return list(self._instances.keys())

    def resolve_class(self, target_id: str, hint_path: Optional[str] = None) -> Optional[type]:
        """Return the *class* for a component without instantiating it.

        ``resolve_class`` and ``resolve`` share the same ``_locate_class``
        discovery pipeline – the only difference is that ``resolve`` also
        instantiates the result (with circuit-breaker protection).
        """
        try:
            cls, _ = self._locate_class(target_id, hint_path)
            if cls is None:
                logger.error("❌ [NEXUS] resolve_class: '%s' não localizado.", target_id)
            return cls
        except Exception as err:
            logger.error("❌ [NEXUS] resolve_class('%s') erro: %s", target_id, err)
            return None

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        """Resolve a component by *target_id*, instantiate and cache it.

        Thread-safe via double-checked locking.  Returns a :class:`CloudMock`
        when the circuit breaker is open or a permanent error occurs.
        """
        start = time.time()

        inst = self._instances.get(target_id)
        if inst is not None and not isinstance(inst, concurrent.futures.Future):
            return inst

        am_builder = False
        pending_future: Optional[concurrent.futures.Future] = None

        with self._lock:
            inst = self._instances.get(target_id)
            if inst is not None and not isinstance(inst, concurrent.futures.Future):
                return inst
            if isinstance(inst, concurrent.futures.Future):
                pending_future = inst
            else:
                if self._is_circuit_open(target_id):
                    logger.warning("☁️ [NEXUS] Circuit Breaker aberto para '%s'. Retornando CloudMock.", target_id)
                    return CloudMock(target_id)
                pending_future = concurrent.futures.Future()
                self._instances[target_id] = pending_future
                am_builder = True

        if not am_builder:
            try:
                return pending_future.result(timeout=CIRCUIT_BREAKER_TIMEOUT + WAITER_TIMEOUT_MARGIN)
            except Exception:
                logger.warning("☁️ [NEXUS] Componente '%s' indisponível. Usando Mock.", target_id)
                return CloudMock(target_id)

        try:
            instance = self._build_instance(target_id, hint_path)
        except Exception as err:
            with self._lock:
                if self._instances.get(target_id) is pending_future:
                    del self._instances[target_id]
            pending_future.set_exception(err)
            return CloudMock(target_id)

        duration_ms = int((time.time() - start) * 1000)
        result_label = "cloudmock" if isinstance(instance, CloudMock) else ("ok" if instance else "none")
        if isinstance(instance, CloudMock):
            logger.warning("☁️ [NEXUS] Componente '%s' indisponível. Usando Mock.", target_id)
        logger.info(
            "⚡ [NEXUS] resolve('%s') → %s em %dms",
            target_id, result_label, duration_ms,
            extra={"component_id": target_id, "duration_ms": duration_ms, "result": result_label},
        )
        if self._metrics_collector is not None:
            try:
                self._metrics_collector.observe("nexus.resolve_duration_ms", duration_ms)
            except Exception:
                pass

        with self._lock:
            if instance and not isinstance(instance, CloudMock):
                self._instances[target_id] = instance
            elif self._instances.get(target_id) is pending_future:
                del self._instances[target_id]

        pending_future.set_result(instance)
        return instance

    def _build_instance(self, target_id: str, hint_path: Optional[str]) -> Any:
        """Submit _resolve_internal to the executor with circuit-breaker timeout."""
        executor = self._get_executor()
        future = executor.submit(self._resolve_internal, target_id, hint_path)
        try:
            return future.result(timeout=CIRCUIT_BREAKER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            self._open_circuit(target_id, f"Timeout após {CIRCUIT_BREAKER_TIMEOUT}s")
            return CloudMock(target_id)
        except Exception as err:
            self._open_circuit(target_id, str(err))
            return CloudMock(target_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
nexus = JarvisNexus()
