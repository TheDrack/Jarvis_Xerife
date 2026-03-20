# -*- coding: utf-8 -*-
"""
JarvisNexus — O Sistema Nervoso Central (Nexus).
Responsável por resolução de dependências, gerenciamento de instâncias e thread-safety.
"""
import concurrent.futures
import logging
import threading
import time
from typing import Any, Dict, Optional

from app.core.nexus_discovery import _NexusDiscoveryMixin
from app.core.nexus_exceptions import (
    CIRCUIT_BREAKER_TIMEOUT,
    WAITER_TIMEOUT_MARGIN,
    CloudMock
)

logger = logging.getLogger(__name__)

class JarvisNexus(_NexusDiscoveryMixin):
    """
    Nexus central para gerenciamento dinâmico de componentes.
    Implementa Singleton e Circuit Breaker para evitar falhas em cascata.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(JarvisNexus, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._instances: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}
        self._cache: Dict[str, str] = {}
        self._circuit_breakers: Dict[str, float] = {}
        self._executor = None
        self._metrics_collector = None
        self._initialized = True
        logger.info("🧠 [NEXUS] Sistema Nervoso Central inicializado.")

    def _get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=10, 
                thread_name_prefix="NexusExecutor"
            )
        return self._executor

    def resolve(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """
        Resolve um componente pelo ID, com proteção global contra falhas.
        [CORREÇÃO]: Adicionado try-except global para gatilhos de self-healing.
        """
        try:
            start = time.time()
            
            # 1. Verificação rápida em cache
            with self._lock:
                inst = self._instances.get(target_id)
                if inst is not None and not isinstance(inst, concurrent.futures.Future):
                    return inst

                # 2. Se já estiver sendo construído por outra thread, espera
                if isinstance(inst, concurrent.futures.Future):
                    pending_future = inst
                    am_builder = False
                else:
                    # Verifica Circuit Breaker
                    if self._is_circuit_open(target_id):
                        return CloudMock(target_id)
                    
                    # Registra que esta thread construirá o objeto
                    pending_future = concurrent.futures.Future()
                    self._instances[target_id] = pending_future
                    am_builder = True

            # 3. Se não for o construtor, aguarda o resultado
            if not am_builder:
                try:
                    return pending_future.result(timeout=CIRCUIT_BREAKER_TIMEOUT + WAITER_TIMEOUT_MARGIN)
                except Exception:
                    logger.warning("☁️ [NEXUS] Timeout esperando resolução de '%s'.", target_id)
                    return CloudMock(target_id)

            # 4. Sou o construtor: executa a lógica de descoberta e instanciação
            instance = None
            try:
                instance = self._build_instance(target_id, hint_path)
            except Exception as err:
                logger.error("❌ [NEXUS] Erro crítico construindo '%s': %s", target_id, err)
                instance = CloudMock(target_id)

            # 5. Finalização
            duration_ms = int((time.time() - start) * 1000)
            with self._lock:
                if instance and not getattr(instance, "__is_cloud_mock__", False):
                    self._instances[target_id] = instance
                else:
                    if self._instances.get(target_id) is pending_future:
                        del self._instances[target_id]
                
                pending_future.set_result(instance)

            logger.info("⚡ [NEXUS] resolve('%s') → %s (%dms)", target_id, "ok" if instance and not getattr(instance, "__is_cloud_mock__", False) else "mock", duration_ms)
            return instance

        except Exception as e:
            # [GATILHO SELF-HEALING]: Captura erro de resolução para o Nexus auto-evoluir
            logger.critical(f"🚨 [NEXUS] Falha catastrófica na resolução de {target_id}: {str(e)}")
            return CloudMock(target_id)

    def _build_instance(self, target_id: str, hint_path: Optional[str]) -> Any:
        executor = self._get_executor()
        # O método _resolve_internal é fornecido pelo DiscoveryMixin
        future = executor.submit(self._resolve_internal, target_id, hint_path)
        try:
            return future.result(timeout=CIRCUIT_BREAKER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            self._open_circuit(target_id, f"Timeout de resolução ({CIRCUIT_BREAKER_TIMEOUT}s)")
            return CloudMock(target_id)
        except Exception as err:
            self._open_circuit(target_id, f"Erro interno: {str(err)}")
            return CloudMock(target_id)

    def _is_circuit_open(self, target_id: str) -> bool:
        expiry = self._circuit_breakers.get(target_id)
        if expiry and time.time() < expiry:
            return True
        if expiry:
            del self._circuit_breakers[target_id]
        return False

    def _open_circuit(self, target_id: str, reason: str):
        logger.warning("🔌 [NEXUS] Circuit Breaker aberto para '%s'. Razão: %s", target_id, reason)
        self._circuit_breakers[target_id] = time.time() + 30  # 30 segundos de cooldown

# Singleton Global
nexus = JarvisNexus()
