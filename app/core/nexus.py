# -*- coding: utf-8 -*-
"""
JarvisNexus - Dynamic Dependency Injection Container

Environment variables:
    NEXUS_TIMEOUT              Wall-clock circuit-breaker timeout in seconds (default: 2.0)
    NEXUS_CIRCUIT_RESET        Cooling-off period before retrying a tripped circuit (default: 60.0)
    NEXUS_IMPORT_TIMEOUT       Fine-grained timeout for importlib.import_module (default: 1.0)
    NEXUS_INSTANTIATE_TIMEOUT  Fine-grained timeout for class instantiation (default: 1.0)
    NEXUS_STRICT_MODE          If 'true', skip filesystem discovery; only use registry cache
                               (default: false)
    NEXUS_GIST_ID              GitHub Gist ID used for remote registry sync (default: '')
    GIST_PAT                   Personal access token for GitHub Gist PATCH calls

Usage – enable strict mode:
    NEXUS_STRICT_MODE=true  # only resolves components already in the registry cache

Usage – plug in a metrics collector:
    class MyCollector:
        def increment(self, name: str) -> None: ...
        def observe(self, name: str, value: float) -> None: ...

    nexus.register_metrics_collector(MyCollector())
"""
import concurrent.futures
import importlib
import inspect
import json
import logging
import os
import time
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable module-level constants (all override-able via env vars)
# ---------------------------------------------------------------------------
_CIRCUIT_BREAKER_TIMEOUT = float(os.getenv("NEXUS_TIMEOUT", "2.0"))
_CIRCUIT_BREAKER_RESET = float(os.getenv("NEXUS_CIRCUIT_RESET", "60.0"))
_NEXUS_IMPORT_TIMEOUT = float(os.getenv("NEXUS_IMPORT_TIMEOUT", "1.0"))
_NEXUS_INSTANTIATE_TIMEOUT = float(os.getenv("NEXUS_INSTANTIATE_TIMEOUT", "1.0"))
_NEXUS_STRICT_MODE = os.getenv("NEXUS_STRICT_MODE", "false").lower() == "true"
# Extra margin added to _CIRCUIT_BREAKER_TIMEOUT when a waiter thread blocks on a Future
_WAITER_TIMEOUT_MARGIN = 1.0


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ImportTimeoutError(Exception):
    """Raised when importlib.import_module exceeds _NEXUS_IMPORT_TIMEOUT."""


class InstantiateTimeoutError(Exception):
    """Raised when class instantiation exceeds _NEXUS_INSTANTIATE_TIMEOUT."""


class AmbiguousComponentError(Exception):
    """Raised when >1 filesystem candidate matches the same component_id."""

    def __init__(self, component_id: str, candidates: List[str]) -> None:
        self.component_id = component_id
        self.candidates = candidates
        super().__init__(
            f"Ambiguous component '{component_id}': {len(candidates)} candidates found: {candidates}"
        )


# ---------------------------------------------------------------------------
# CloudMock
# ---------------------------------------------------------------------------

class CloudMock:
    """
    Fallback/Mock component injected by the Nexus Circuit Breaker when a real
    component is unavailable or times out.  Absorbs any method call gracefully.
    """

    __is_cloud_mock__ = True

    def __init__(self, component_id: str = "unknown") -> None:
        self._component_id = component_id
        self._call_count: int = 0
        self._last_calls: List[Dict[str, Any]] = []
        self._metrics_collector: Optional[Any] = None

    def __getattr__(self, name: str):
        def _noop(*args, **kwargs):
            self._call_count += 1
            record = {"method": name, "args": args, "kwargs": kwargs}
            self._last_calls.append(record)
            if len(self._last_calls) > 10:
                self._last_calls = self._last_calls[-10:]
            logger.warning(
                f"☁️ [CloudMock] '{self._component_id}.{name}' chamado no fallback "
                f"(componente real indisponível).",
                extra={"component_id": self._component_id, "method": name},
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
            f"☁️ [CloudMock] execute() chamado para '{self._component_id}' (componente indisponível)."
        )
        return {"success": False, "fallback": True, "component": self._component_id}


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
# JarvisNexus
# ---------------------------------------------------------------------------

class JarvisNexus:
    """
    Thread-safe dependency injection container for Jarvis components.

    Uses a circuit breaker pattern to degrade gracefully when a component
    hangs or fails to instantiate.  Caches resolved instances and supports
    optional synchronisation with a remote GitHub Gist registry.
    """

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

    # ------------------------------------------------------------------
    # Executor (lazy, persistent – avoids blocking shutdown on timeout)
    # ------------------------------------------------------------------

    def _get_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="nexus"
            )
        return self._executor

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def register_metrics_collector(self, collector: Any) -> None:
        """Register an object with increment(name) and observe(name, value)."""
        self._metrics_collector = collector

    # ------------------------------------------------------------------
    # DNA loader
    # ------------------------------------------------------------------

    def load_dna(self, dna_dict: dict) -> None:
        self.dna = dna_dict
        components = dna_dict.get("components", {})
        for c_id, meta in components.items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    # ------------------------------------------------------------------
    # Circuit Breaker helpers
    # ------------------------------------------------------------------

    def _is_circuit_open(self, target_id: str) -> bool:
        """Return True when the circuit is still in its cooling-off period."""
        entry = self._circuit_breaker.get(target_id)
        if entry is None:
            return False
        if time.monotonic() - entry.open_at < _CIRCUIT_BREAKER_RESET:
            return True
        # Cooling-off elapsed – reset and allow retry
        del self._circuit_breaker[target_id]
        return False

    def _open_circuit(self, target_id: str, reason: str) -> None:
        """Trip the circuit for *target_id* and record the failure reason."""
        entry = _CircuitBreakerEntry()
        entry.open_at = time.monotonic()
        entry.last_failure = reason
        self._circuit_breaker[target_id] = entry
        logger.error(
            f"⚡ [NEXUS] Circuit Breaker ABERTO para '{target_id}': {reason}. "
            f"Injetando CloudMock por {_CIRCUIT_BREAKER_RESET}s."
        )

    # ------------------------------------------------------------------
    # Resolution pipeline
    # ------------------------------------------------------------------

    def _resolve_with_timeout(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """
        Call _resolve_internal via the thread-pool executor, enforcing
        _CIRCUIT_BREAKER_TIMEOUT.  The underlying thread continues in the
        background if it times out (CPython limitation); this is intentional.
        """
        executor = self._get_executor()
        future = executor.submit(self._resolve_internal, target_id, hint_path)
        try:
            return future.result(timeout=_CIRCUIT_BREAKER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            self._open_circuit(target_id, f"Timeout após {_CIRCUIT_BREAKER_TIMEOUT}s")
            return CloudMock(target_id)
        except Exception as err:
            self._open_circuit(target_id, str(err))
            return CloudMock(target_id)

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        """
        Resolve a component by *target_id*, with thread-safe double-checked
        locking and circuit-breaker protection.
        """
        start = time.time()

        # --- Fast path: already cached (no lock needed for a dict read) ---
        inst = self._instances.get(target_id)
        if inst is not None and not isinstance(inst, concurrent.futures.Future):
            return inst

        # --- Slow path: acquire lock for double-checked access ---
        am_builder = False
        pending_future: Optional[concurrent.futures.Future] = None

        with self._lock:
            inst = self._instances.get(target_id)
            if inst is not None and not isinstance(inst, concurrent.futures.Future):
                return inst

            if isinstance(inst, concurrent.futures.Future):
                # Another thread is already building this component
                pending_future = inst
            else:
                # We are the first – check circuit breaker before committing
                if self._is_circuit_open(target_id):
                    logger.warning(
                        f"☁️ [NEXUS] Circuit Breaker aberto para '{target_id}'. Retornando CloudMock."
                    )
                    return CloudMock(target_id)
                # Plant a Future placeholder so other threads can wait on us
                pending_future = concurrent.futures.Future()
                self._instances[target_id] = pending_future
                am_builder = True

        # --- Wait branch: another thread is building ---
        if not am_builder:
            try:
                return pending_future.result(timeout=_CIRCUIT_BREAKER_TIMEOUT + _WAITER_TIMEOUT_MARGIN)
            except Exception:
                return CloudMock(target_id)

        # --- Build branch: we own the resolution ---
        try:
            instance = self._resolve_with_timeout(target_id, hint_path)
        except Exception as err:
            with self._lock:
                if self._instances.get(target_id) is pending_future:
                    del self._instances[target_id]
            pending_future.set_exception(err)
            return CloudMock(target_id)

        duration_ms = int((time.time() - start) * 1000)
        result_label = (
            "cloudmock" if isinstance(instance, CloudMock)
            else ("ok" if instance else "none")
        )
        logger.info(
            "nexus.resolve",
            extra={
                "component_id": target_id,
                "duration_ms": duration_ms,
                "result": result_label,
            },
        )
        if self._metrics_collector is not None:
            try:
                self._metrics_collector.observe("nexus.resolve_duration_ms", duration_ms)
            except Exception:
                pass

        # Cache real instances; remove placeholder on failure/mock
        with self._lock:
            if instance and not isinstance(instance, CloudMock):
                self._instances[target_id] = instance
            elif self._instances.get(target_id) is pending_future:
                del self._instances[target_id]

        pending_future.set_result(instance)
        return instance

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """Core resolution logic (no outer timeout logic here)."""
        # 1. Explicit hint path
        if hint_path:
            instance = self._instantiate_from_path(hint_path, target_id)
            if instance:
                return instance

        # 2. Registered path (DNA / local cache)
        stored_path = self._cache.get(target_id)
        if stored_path is None:
            stored_path = self._path_map.get(target_id)
        if stored_path:
            instance = self._instantiate_from_path(stored_path, target_id)
            if instance:
                return instance

        # 3. Strict mode: no filesystem discovery
        if _NEXUS_STRICT_MODE:
            logger.error(f"❌ [NEXUS] Strict mode: '{target_id}' não encontrado no registro.")
            return None

        # 4. Filesystem discovery
        logger.info(f"🔍 [NEXUS] Iniciando varredura em disco para localizar '{target_id}'...")
        instance, real_path = self._global_search_with_path(target_id)

        if instance:
            if hint_path or stored_path:
                logger.error(
                    f"🚨 [NEXUS] CORREÇÃO: '{target_id}' achado em '{real_path}' (Diferente do esperado)."
                )
            else:
                logger.info(f"⚡ [NEXUS] '{target_id}' localizado em '{real_path}'")
            self._path_map[target_id] = real_path
            return instance

        logger.error(f"❌ [NEXUS] Falha total: '{target_id}' não localizado no projeto.")
        return None

    def _instantiate_from_path(self, module_path: str, target_id: str) -> Any:
        """
        Import a module and instantiate the matching class, enforcing fine-grained
        per-step timeouts via the shared executor.
        """
        try:
            # Normalise: 'app/services/file.py' -> 'app.services.file'
            clean_path = module_path.replace("/", ".").replace("\\", ".").replace(".py", "")
            if clean_path.startswith("."):
                clean_path = clean_path[1:]

            executor = self._get_executor()

            # Fine-grained import timeout
            import_future = executor.submit(importlib.import_module, clean_path)
            try:
                module = import_future.result(timeout=_NEXUS_IMPORT_TIMEOUT)
            except concurrent.futures.TimeoutError:
                raise ImportTimeoutError(f"Import timeout for '{clean_path}'")

            norm_target = target_id.replace("_", "").lower()

            for name, obj in inspect.getmembers(module, inspect.isclass):
                norm_class = name.replace("_", "").lower()
                if norm_class == norm_target or name.lower() == target_id.lower():
                    # Fine-grained instantiation timeout
                    inst_future = executor.submit(obj)
                    try:
                        return inst_future.result(timeout=_NEXUS_INSTANTIATE_TIMEOUT)
                    except concurrent.futures.TimeoutError:
                        raise InstantiateTimeoutError(f"Instantiation timeout for '{name}'")

        except (ImportTimeoutError, InstantiateTimeoutError):
            raise  # Propagate so _resolve_with_timeout can open the circuit
        except Exception:
            return None
        return None

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[Any], Optional[str]]:
        """
        Walk the filesystem under ``app/`` for a matching component.

        Raises AmbiguousComponentError when more than one file yields a valid
        instance – forces the developer to register the component explicitly.
        """
        base_dir = os.path.abspath(os.path.join(os.getcwd(), "app"))
        norm_target = target_id.replace("_", "").lower()
        candidates: List[Tuple[Any, str]] = []

        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if (
                        target_id.lower() in file.lower()
                        or norm_target in file.lower().replace("_", "")
                    ):
                        relative_path = os.path.relpath(os.path.join(root, file), os.getcwd())
                        module_path = relative_path.replace(os.sep, ".").replace(".py", "")
                        instance = self._instantiate_from_path(module_path, target_id)
                        if instance:
                            candidates.append((instance, module_path))

        if len(candidates) > 1:
            candidate_paths = [p for _, p in candidates]
            logger.error(
                f"🔀 [NEXUS] Ambiguous '{target_id}': "
                f"{len(candidates)} candidates: {candidate_paths}"
            )
            raise AmbiguousComponentError(target_id, candidate_paths)

        if candidates:
            return candidates[0]
        return None, None

    # ------------------------------------------------------------------
    # Local registry helpers
    # ------------------------------------------------------------------

    def _load_local_registry(self) -> Dict[str, str]:
        """
        Read nexus_registry.json from base_dir and strip the trailing
        ``.ClassName`` suffix from each stored path.
        """
        try:
            registry_path = os.path.join(self.base_dir, "nexus_registry.json")
            with open(registry_path) as f:
                data = json.load(f)
            result: Dict[str, str] = {}
            for component_id, path in data.get("components", {}).items():
                parts = path.rsplit(".", 1)
                # Strip trailing ClassName if the last segment starts with uppercase
                if len(parts) == 2 and parts[1] and parts[1][0].isupper():
                    result[component_id] = parts[0]
                else:
                    result[component_id] = path
            return result
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _load_remote_memory(self) -> Dict[str, str]:
        """Fetch the component registry from the configured GitHub Gist."""
        try:
            import requests  # noqa: PLC0415

            gist_id = getattr(self, "gist_id", "")
            if not gist_id:
                return {}
            response = requests.get(f"https://api.github.com/gists/{gist_id}")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}

    def _update_local_registry(self) -> None:
        """
        Write _cache back to nexus_registry.json, appending the inferred
        ``.ClassName`` suffix so the file remains human-readable.
        """
        components: Dict[str, str] = {}
        for component_id, module_path in self._cache.items():
            last_segment = module_path.rsplit(".", 1)[-1]
            class_name = "".join(part.capitalize() for part in last_segment.split("_"))
            components[component_id] = f"{module_path}.{class_name}"
        registry_path = os.path.join(self.base_dir, "nexus_registry.json")
        with open(registry_path, "w") as f:
            json.dump({"components": components}, f, indent=2)

    # ------------------------------------------------------------------
    # Gist sync
    # ------------------------------------------------------------------

    def commit_memory(self) -> None:
        """
        Push _cache to the configured GitHub Gist and update the local
        registry on confirmed success (HTTP 200).

        Retries up to 3 times with exponential back-off (0.1s, 0.2s).
        _update_local_registry() is called *only* after a confirmed 200.
        """
        import requests  # noqa: PLC0415

        if not getattr(self, "_mutated", False):
            return

        gist_pat = os.getenv("GIST_PAT", "")
        if not gist_pat:
            logger.warning("[NEXUS] No GIST_PAT set; skipping gist sync.")
            return

        cache = getattr(self, "_cache", {})
        # Validate payload: every value must be a module-path string
        if not isinstance(cache, dict) or not all(isinstance(v, str) for v in cache.values()):
            logger.error("[NEXUS] Invalid cache structure; aborting gist sync.")
            return

        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {
            "Authorization": f"token {gist_pat}",
            "Accept": "application/vnd.github.v3+json",
        }

        for attempt in range(3):
            try:
                response = requests.patch(url, headers=headers, json=cache)
                if response.status_code == 200:
                    self._update_local_registry()
                    self._mutated = False
                    return
                logger.warning(
                    f"[NEXUS] Gist patch attempt {attempt + 1} returned {response.status_code}."
                )
            except Exception as err:
                logger.error(f"[NEXUS] Gist patch attempt {attempt + 1} exception: {err}.")
            if attempt < 2:
                time.sleep(0.1 * (2 ** attempt))  # 0.1s then 0.2s before the 2nd and 3rd tries

        logger.error("[NEXUS] All gist patch attempts failed; _mutated remains True.")


nexus = JarvisNexus()
