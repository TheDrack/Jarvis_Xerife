# -*- coding: utf-8 -*-
"""
JarvisNexus – Dynamic Dependency Injection Container.
Corrigido: Thread-safety no Circuit Breaker e gestão de Futures.
"""
import concurrent.futures
import logging
import os
import time
import threading
from threading import RLock
from typing import Any, Dict, Optional, List

from app.core.nexus_exceptions import (
    CIRCUIT_BREAKER_RESET,
    CIRCUIT_BREAKER_TIMEOUT,
    WAITER_TIMEOUT_MARGIN,
    CloudMock,
    _CircuitBreakerEntry,
)
from app.core.nexus_discovery import _NexusDiscoveryMixin
from app.core.nexus_registry import _NexusRegistryMixin
from app.core.nexuscomponent import NexusComponent  # noqa: F401

# Re-export helpers
from app.core.nexus_exceptions import (  # noqa: F401
    AmbiguousComponentError,
    ImportTimeoutError,
    InstantiateTimeoutError,
    nexus_guarded_instantiate as _nexus_guarded_instantiate,
)

logger = logging.getLogger(__name__)

__all__ = [
    "JarvisNexus",
    "NexusComponent",
    "CloudMock",
    "nexus",
]

class JarvisNexus(_NexusDiscoveryMixin, _NexusRegistryMixin):
    """Contêiner DI Thread-safe com Circuit-Breaker e Descoberta Dinâmica."""
    
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
        
        # Inicializa registro local herdado de RegistryMixin
        try:
            self._cache.update(self._load_local_registry())
        except Exception as e:
            logger.error("❌ [NEXUS] Falha ao carregar registro local: %s", e)

    def _get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        """Retorna o executor lazy-loaded com proteção de lock."""
        if self._executor is None:
            with self._lock:
                if self._executor is None:
                    self._executor = concurrent.futures.ThreadPoolExecutor(
                        max_workers=4, thread_name_prefix="nexus_resolver"
                    )
        return self._executor

    def register_metrics_collector(self, collector: Any) -> None:
        self._metrics_collector = collector

    def load_dna(self, dna_dict: dict) -> None:
        with self._lock:
            self.dna = dna_dict
            for c_id, meta in dna_dict.get("components", {}).items():
                if "hint_path" in meta:
                    self._path_map[c_id] = meta["hint_path"]

    # ------------------------------------------------------------------
    # Circuit Breaker (Thread-Safe)
    # ------------------------------------------------------------------
    def _is_circuit_open(self, target_id: str) -> bool:
        with self._lock:
            entry = self._circuit_breaker.get(target_id)
            if entry is None:
                return False
            if time.monotonic() - entry.open_at < CIRCUIT_BREAKER_RESET:
                return True
            # Cooling-off period expired
            del self._circuit_breaker[target_id]
            return False

    def _open_circuit(self, target_id: str, reason: str) -> None:
        with self._lock:
            entry = _CircuitBreakerEntry()
            entry.open_at = time.monotonic()
            entry.last_failure = reason
            self._circuit_breaker[target_id] = entry
            logger.error(
                "⚡ [NEXUS] Circuit Breaker ABERTO para '%s': %s. Fallback ativado por %.0fs.",
                target_id, reason, CIRCUIT_BREAKER_RESET,
            )

    def invalidate_component(self, component_id: str) -> None:
        """Remove o componente do cache, instâncias e reseta o circuit breaker."""
        with self._lock:
            self._cache.pop(component_id, None)
            self._instances.pop(component_id, None)
            self._circuit_breaker.pop(component_id, None)
            self._mutated = True
            logger.info("♻️ [NEXUS] Componente '%s' invalidado e removido do cache.", component_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_loaded_ids(self) -> List[str]:
        with self._lock:
            return [k for k, v in self._instances.items() if not isinstance(v, concurrent.futures.Future)]

    def resolve_class(self, target_id: str, hint_path: Optional[str] = None) -> Optional[type]:
        """Localiza a classe sem instanciar (bypass circuit-breaker)."""
        try:
            cls, _ = self._locate_class(target_id, hint_path)
            return cls
        except Exception as err:
            logger.error("❌ [NEXUS] Erro ao localizar classe '%s': %s", target_id, err)
            return None

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        """Resolve, instancia e faz cache do componente com proteção de circuit-breaker."""
        start = time.time()
        
        # 1. Fast Path: Já existe?
        with self._lock:
            inst = self._instances.get(target_id)
            if inst is not None and not isinstance(inst, concurrent.futures.Future):
                return inst

        # 2. Slow Path: Coalescência de Threads (Double-Checked Locking)
        am_builder = False
        pending_future: Optional[concurrent.futures.Future] = None
        
        with self._lock:
            inst = self._instances.get(target_id)
            # Re-check após lock
            if inst is not None and not isinstance(inst, concurrent.futures.Future):
                return inst
            
            if isinstance(inst, concurrent.futures.Future):
                pending_future = inst
            else:
                # Verifica Circuit Breaker antes de tentar criar
                if self._is_circuit_open(target_id):
                    return CloudMock(target_id)
                
                # Registra que esta thread vai construir o objeto
                pending_future = concurrent.futures.Future()
                self._instances[target_id] = pending_future
                am_builder = True
        
        # 3. Se não sou o construtor, espero o resultado do outro
        if not am_builder:
            try:
                # Timeout marginal para evitar deadlocks se o builder travar
                return pending_future.result(timeout=CIRCUIT_BREAKER_TIMEOUT + WAITER_TIMEOUT_MARGIN)
            except Exception:
                logger.warning("☁️ [NEXUS] Timeout esperando resolução de '%s'.", target_id)
                return CloudMock(target_id)
        
        # 4. Sou o construtor: executo a construção
        instance = None
        try:
            instance = self._build_instance(target_id, hint_path)
        except Exception as err:
            logger.error("❌ [NEXUS] Erro crítico construindo '%s': %s", target_id, err)
            instance = CloudMock(target_id)
        
        # 5. Finalização e Métricas
        duration_ms = int((time.time() - start) * 1000)
        
        with self._lock:
            # Se for um sucesso real, guarda a instância. Se for Mock, limpa para tentar de novo no futuro
            if instance and not getattr(instance, "__is_cloud_mock__", False):
                self._instances[target_id] = instance
            else:
                # Se falhou, removemos o Future para que a próxima chamada dispare o Circuit Breaker
                if self._instances.get(target_id) is pending_future:
                    del self._instances[target_id]
            
            # Notifica todas as threads que estavam esperando no .result()
            pending_future.set_result(instance)

        # Log e Telemetria
        result_label = "mock" if getattr(instance, "__is_cloud_mock__", False) else "ok"
        logger.info("⚡ [NEXUS] resolve('%s') → %s (%dms)", target_id, result_label, duration_ms)
        
        if self._metrics_collector:
            try:
                self._metrics_collector.observe("nexus.resolve_duration_ms", duration_ms)
            except Exception: pass
            
        return instance

    def _build_instance(self, target_id: str, hint_path: Optional[str]) -> Any:
        """Executa a lógica de importação e instanciação dentro do executor para controle de timeout."""
        executor = self._get_executor()
        # _resolve_internal vem de DiscoveryMixin/RegistryMixin
        future = executor.submit(self._resolve_internal, target_id, hint_path)
        
        try:
            return future.result(timeout=CIRCUIT_BREAKER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            self._open_circuit(target_id, f"Timeout de resolução ({CIRCUIT_BREAKER_TIMEOUT}s)")
            return CloudMock(target_id)
        except Exception as err:
            self._open_circuit(target_id, f"Erro interno: {str(err)}")
            return CloudMock(target_id)

# Singleton global
nexus = JarvisNexus()
