# -*- coding: utf-8 -*-
"""
_NexusDiscoveryMixin – class-finding and filesystem traversal logic for JarvisNexus.

Provides ``_locate_class``, ``_find_module_class``, ``_global_search_class`` and
``_locate_and_instantiate``, all mixed into JarvisNexus so the main module stays
focused on the public API and thread-safety plumbing.
"""
import concurrent.futures
import importlib
import inspect
import logging
import os
from typing import Any, List, Optional, Tuple

from app.core.nexus_exceptions import (
    NEXUS_IMPORT_TIMEOUT,
    NEXUS_INSTANTIATE_TIMEOUT,
    NEXUS_STRICT_MODE,
    AmbiguousComponentError,
    ImportTimeoutError,
    InstantiateTimeoutError,
    nexus_guarded_instantiate,
)

logger = logging.getLogger(__name__)


class _NexusDiscoveryMixin:
    """Filesystem-based component discovery helpers mixed into JarvisNexus."""

    # ------------------------------------------------------------------
    # Module / class finders
    # ------------------------------------------------------------------

    def _find_class_from_path(self, module_path: str, target_id: str) -> Optional[type]:
        """Import *module_path* and return the first class whose normalised name
        matches *target_id*.  Returns ``None`` on any failure.
        """
        try:
            clean = module_path.replace("/", ".").replace("\\", ".").replace(".py", "").lstrip(".")
            executor = self._get_executor()  # type: ignore[attr-defined]
            fut = executor.submit(importlib.import_module, clean)
            try:
                module = fut.result(timeout=NEXUS_IMPORT_TIMEOUT)
            except concurrent.futures.TimeoutError:
                raise ImportTimeoutError(f"Import timeout for '{clean}'")
            norm = target_id.replace("_", "").lower()
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.replace("_", "").lower() == norm or name.lower() == target_id.lower():
                    return obj  # type: ignore[return-value]
        except (ImportTimeoutError, InstantiateTimeoutError):
            raise
        except Exception:
            pass
        return None

    @staticmethod
    def _find_file_in_dir(directory: str, target_id: str) -> Optional[str]:
        """Return the first matching ``.py`` file path inside *directory*."""
        norm = target_id.replace("_", "").lower()
        try:
            for fname in os.listdir(directory):
                if fname.endswith(".py") and not fname.startswith("__"):
                    if target_id.lower() in fname.lower() or norm in fname.lower().replace("_", ""):
                        return os.path.join(directory, fname)
        except OSError:
            pass
        return None

    # ------------------------------------------------------------------
    # Location pipeline (shared by resolve() and resolve_class())
    # ------------------------------------------------------------------

    def _locate_class(
        self, target_id: str, hint_path: Optional[str] = None
    ) -> Tuple[Optional[type], Optional[str]]:
        """Find the class for *target_id*.  Returns ``(cls, module_path)`` or ``(None, None)``.

        Search order:
        1. Explicit hint_path (file or directory).
        2. Registered path in local cache / DNA path map.
        3. Filesystem discovery (skipped when NEXUS_STRICT_MODE is true).
        """
        # 1. Explicit hint
        if hint_path:
            path = hint_path
            if os.path.isdir(path):
                path = self._find_file_in_dir(path, target_id) or path
            cls = self._find_class_from_path(path, target_id)
            if cls is not None:
                return cls, path

        # 2. Registered / cached path
        stored = self._cache.get(target_id) or self._path_map.get(target_id)  # type: ignore[attr-defined]
        if stored:
            cls = self._find_class_from_path(stored, target_id)
            if cls is not None:
                return cls, stored

        # 3. Filesystem discovery
        if NEXUS_STRICT_MODE:
            logger.error("❌ [NEXUS] Strict mode: '%s' não encontrado no registro.", target_id)
            return None, None

        logger.info("🔍 [NEXUS] Varredura em disco para '%s'...", target_id)
        return self._global_search_with_path(target_id)

    def _global_search_with_path(
        self, target_id: str
    ) -> Tuple[Optional[type], Optional[str]]:
        """Walk ``app/`` for a class matching *target_id*.

        Raises :class:`AmbiguousComponentError` when more than one file matches.
        """
        base_dir = os.path.abspath(os.path.join(os.getcwd(), "app"))
        norm = target_id.replace("_", "").lower()
        candidates: List[Tuple[type, str]] = []

        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    if target_id.lower() in file.lower() or norm in file.lower().replace("_", ""):
                        rel = os.path.relpath(os.path.join(root, file), os.getcwd())
                        mod_path = rel.replace(os.sep, ".").replace(".py", "")
                        cls = self._find_class_from_path(mod_path, target_id)
                        if cls is not None:
                            candidates.append((cls, mod_path))

        if len(candidates) > 1:
            paths = [p for _, p in candidates]
            logger.error(
                "🔀 [NEXUS] Ambiguous '%s': %d candidates: %s", target_id, len(candidates), paths
            )
            raise AmbiguousComponentError(target_id, paths)

        return candidates[0] if candidates else (None, None)

    # ------------------------------------------------------------------
    # Instantiation (runs inside the executor thread)
    # ------------------------------------------------------------------

    def _resolve_internal(self, target_id: str, hint_path: Optional[str]) -> Any:
        """Locate the class and instantiate it (called inside executor)."""
        cls, real_path = self._locate_class(target_id, hint_path)
        if cls is None:
            logger.error("❌ [NEXUS] Falha total: '%s' não localizado no projeto.", target_id)
            return None

        hint_or_stored = (
            hint_path
            or self._cache.get(target_id)  # type: ignore[attr-defined]
            or self._path_map.get(target_id)  # type: ignore[attr-defined]
        )
        if hint_or_stored and real_path and real_path != hint_or_stored:
            logger.error(
                "🚨 [NEXUS] CORREÇÃO: '%s' achado em '%s' (Diferente do esperado).",
                target_id, real_path,
            )
        else:
            logger.info("⚡ [NEXUS] '%s' localizado em '%s'", target_id, real_path)

        if real_path:
            self._path_map[target_id] = real_path  # type: ignore[attr-defined]

        executor = self._get_executor()  # type: ignore[attr-defined]
        inst_future = executor.submit(nexus_guarded_instantiate, cls)
        try:
            return inst_future.result(timeout=NEXUS_INSTANTIATE_TIMEOUT)
        except concurrent.futures.TimeoutError:
            raise InstantiateTimeoutError(f"Instantiation timeout for '{cls.__name__}'")
