# -*- coding: utf-8 -*-
import importlib
import inspect
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Circuit Breaker constants
_CIRCUIT_BREAKER_TIMEOUT = 2.0  # seconds before marking a component as failed
_CIRCUIT_BREAKER_RESET = 60.0   # seconds before retrying a failed component


class CloudMock:
    """
    Fallback/Mock component injected by the Nexus Circuit Breaker when a real
    component is unavailable or times out.  It absorbs any method call gracefully.
    """

    def __init__(self, component_id: str = "unknown"):
        self._component_id = component_id

    def __getattr__(self, name: str):
        def _noop(*args, **kwargs):
            logger.warning(
                f"☁️ [CloudMock] '{self._component_id}.{name}' chamado no fallback "
                f"(componente real indisponível)."
            )
            return None
        return _noop

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.warning(
            f"☁️ [CloudMock] execute() chamado para '{self._component_id}' (componente indisponível)."
        )
        return {"success": False, "fallback": True, "component": self._component_id}


class _CircuitBreakerEntry:
    """Internal state for one component inside the circuit breaker."""

    __slots__ = ("open_at", "last_failure")

    def __init__(self):
        self.open_at: float = 0.0       # timestamp when the circuit opened
        self.last_failure: str = ""     # last error message


class JarvisNexus:
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self.dna: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}
        self._circuit_breaker: Dict[str, _CircuitBreakerEntry] = {}

    def load_dna(self, dna_dict: dict):
        self.dna = dna_dict
        components = dna_dict.get("components", {})
        for c_id, meta in components.items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    # ------------------------------------------------------------------
    # Circuit Breaker helpers
    # ------------------------------------------------------------------

    def _is_circuit_open(self, target_id: str) -> bool:
        """Returns True if the circuit is open (component still in cooling-off period)."""
        entry = self._circuit_breaker.get(target_id)
        if entry is None:
            return False
        if time.monotonic() - entry.open_at < _CIRCUIT_BREAKER_RESET:
            return True
        # Reset after cooling-off period — try again
        del self._circuit_breaker[target_id]
        return False

    def _open_circuit(self, target_id: str, reason: str) -> None:
        """Open the circuit for *target_id* and log the reason."""
        entry = _CircuitBreakerEntry()
        entry.open_at = time.monotonic()
        entry.last_failure = reason
        self._circuit_breaker[target_id] = entry
        logger.error(
            f"⚡ [NEXUS] Circuit Breaker ABERTO para '{target_id}': {reason}. "
            f"Injetando CloudMock por {_CIRCUIT_BREAKER_RESET}s."
        )

    def _resolve_with_timeout(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """
        Try to instantiate the component, enforcing a wall-clock timeout.

        Note: The worker thread is marked as a *daemon* thread so it does not
        prevent process exit.  If it times out, it may continue running in the
        background and eventually complete its work — this is intentional:
        the thread cannot be forcibly cancelled in CPython.  Any side effects
        it produces (e.g. populating ``_instances``) are benign because the
        successfully resolved instance is cached on first use.
        """
        import threading

        result: Dict[str, Any] = {"instance": None}

        def _worker():
            result["instance"] = self._resolve_internal(target_id, hint_path)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=_CIRCUIT_BREAKER_TIMEOUT)

        if thread.is_alive():
            reason = f"Timeout após {_CIRCUIT_BREAKER_TIMEOUT}s"
            self._open_circuit(target_id, reason)
            return CloudMock(target_id)

        return result["instance"]

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        if target_id in self._instances:
            return self._instances[target_id]

        # Circuit Breaker: return mock immediately if circuit is still open
        if self._is_circuit_open(target_id):
            logger.warning(
                f"☁️ [NEXUS] Circuit Breaker aberto para '{target_id}'. Retornando CloudMock."
            )
            return CloudMock(target_id)

        instance = self._resolve_with_timeout(target_id, hint_path)

        if instance and not isinstance(instance, CloudMock):
            self._instances[target_id] = instance

        return instance

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """Core resolution logic (no timeout logic here)."""
        # 1. Tentar Hint Explícito
        if hint_path:
            instance = self._instantiate_from_path(hint_path, target_id)
            if instance:
                return instance

        # 2. Consultar Mapa Interno (DNA)
        stored_path = self._path_map.get(target_id)
        if stored_path:
            instance = self._instantiate_from_path(stored_path, target_id)
            if instance:
                return instance

        # 3. Busca Global (Cura via Varredura de Disco)
        logger.info(f"🔍 [NEXUS] Iniciando varredura em disco para localizar '{target_id}'...")
        instance, real_path = self._global_search_with_path(target_id)

        if instance:
            if hint_path or stored_path:
                logger.error(f"🚨 [NEXUS] CORREÇÃO: '{target_id}' achado em '{real_path}' (Diferente do esperado).")
            else:
                logger.info(f"⚡ [NEXUS] '{target_id}' localizado em '{real_path}'")

            self._path_map[target_id] = real_path
            return instance

        logger.error(f"❌ [NEXUS] Falha total: '{target_id}' não localizado no projeto.")
        return None

    def _instantiate_from_path(self, module_path: str, target_id: str) -> Any:
        """Tenta instanciar convertendo caminhos de arquivo ou módulos Python."""
        try:
            # Normaliza: 'app/services/file.py' -> 'app.services.file'
            clean_path = module_path.replace("/", ".").replace("\\", ".").replace(".py", "")
            if clean_path.startswith("."): clean_path = clean_path[1:]

            module = importlib.import_module(clean_path)
            norm_target = target_id.replace("_", "").lower()

            for name, obj in inspect.getmembers(module, inspect.isclass):
                norm_class = name.replace("_", "").lower()
                if norm_class == norm_target or name.lower() == target_id.lower():
                    return obj()
        except Exception:
            return None
        return None

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[Any], Optional[str]]:
        """Varredura real no sistema de arquivos para garantir a localização."""
        base_dir = os.path.abspath(os.path.join(os.getcwd(), "app"))
        norm_target = target_id.replace("_", "").lower()

        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    # Verifica se o nome do arquivo contém o ID procurado
                    if target_id.lower() in file.lower() or norm_target in file.lower().replace("_", ""):
                        # Converte o caminho do arquivo em caminho de módulo Python
                        relative_path = os.path.relpath(os.path.join(root, file), os.getcwd())
                        module_path = relative_path.replace(os.sep, ".").replace(".py", "")

                        instance = self._instantiate_from_path(module_path, target_id)
                        if instance:
                            return instance, module_path
        return None, None

nexus = JarvisNexus()
