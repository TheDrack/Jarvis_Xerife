# -*- coding: utf-8 -*-
"""
_NexusDiscoveryMixin – Lógica de busca de classes e travessia de arquivos.
[CORREÇÃO]: Otimizado para funcionar em ambientes Render/Docker.
"""
import concurrent.futures
import importlib
import inspect
import logging
import os
from typing import Any, List, Optional, Tuple, Dict
from app.core.nexus_exceptions import (
    NEXUS_IMPORT_TIMEOUT,
    NEXUS_STRICT_MODE,
    AmbiguousComponentError,
    ImportTimeoutError,
    nexus_guarded_instantiate
)

logger = logging.getLogger(__name__)

class _NexusDiscoveryMixin:
    """Helper de descoberta baseado em sistema de arquivos para o JarvisNexus."""

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        """Lógica interna de localização e instanciação."""
        cls, path = self._locate_class(target_id, hint_path)
        if not cls:
            return None
        
        # Instanciação protegida (evita crash do core por erros no __init__ do componente)
        return nexus_guarded_instantiate(cls)

    def _locate_class(self, target_id: str, hint_path: Optional[str] = None) -> Tuple[Optional[type], Optional[str]]:
        # 1. Hint explícito
        if hint_path:
            path = hint_path
            if os.path.isdir(path):
                path = self._find_file_in_dir(path, target_id) or path
            cls = self._find_class_from_path(path, target_id)
            if cls: return cls, path

        # 2. Verificação no registro/cache (DNA)
        stored = getattr(self, "_cache", {}).get(target_id) or getattr(self, "_path_map", {}).get(target_id)
        if stored:
            cls = self._find_class_from_path(stored, target_id)
            if cls: return cls, stored

        # 3. Varredura no disco (se não estiver em modo estrito)
        if NEXUS_STRICT_MODE:
            logger.error("❌ [NEXUS] Strict mode: '%s' não encontrado no registro.", target_id)
            return None, None

        return self._global_search_with_path(target_id)

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[type], Optional[str]]:
        """
        Varre o diretório 'app/' em busca de uma classe que case com o target_id.
        [CORREÇÃO]: Lógica de root dinâmica para Render.
        """
        # Define o root de busca: prioriza o diretório de execução atual
        current_dir = os.getcwd()
        search_root = os.path.join(current_dir, "app")
        
        if not os.path.exists(search_root):
            # Fallback para o root absoluto do projeto caso app/ não esteja no CWD
            search_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if not search_root.endswith("app"):
                search_root = os.path.join(search_root, "app")

        matches: List[Tuple[type, str]] = []
        norm_target = target_id.replace("_", "").lower()

        for root, _, files in os.walk(search_root):
            if "__pycache__" in root: continue
            
            for fname in files:
                if fname.endswith(".py") and not fname.startswith("__"):
                    # Match heurístico no nome do arquivo
                    if target_id.lower() in fname.lower() or norm_target in fname.lower().replace("_", ""):
                        full_path = os.path.join(root, fname)
                        cls = self._find_class_from_path(full_path, target_id)
                        if cls:
                            matches.append((cls, full_path))

        if not matches:
            return None, None
        
        if len(matches) > 1:
            # Se houver ambiguidade, prioriza o que tiver o nome mais exato
            for cls, path in matches:
                if cls.__name__.lower() == target_id.lower():
                    return cls, path
            raise AmbiguousComponentError(f"Múltiplos candidatos para '{target_id}': {[m[1] for m in matches]}")

        return matches[0]

    def _find_class_from_path(self, module_path: str, target_id: str) -> Optional[type]:
        try:
            # Converte path de arquivo em path de módulo (ex: app/core/nexus.py -> app.core.nexus)
            rel_path = os.path.relpath(module_path, os.getcwd())
            clean = rel_path.replace("/", ".").replace("\\", ".").replace(".py", "").lstrip(".")
            
            executor = self._get_executor() # type: ignore
            fut = executor.submit(importlib.import_module, clean)
            try:
                module = fut.result(timeout=NEXUS_IMPORT_TIMEOUT)
            except concurrent.futures.TimeoutError:
                raise ImportTimeoutError(f"Import timeout para '{clean}'")

            norm = target_id.replace("_", "").lower()
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.replace("_", "").lower() == norm or name.lower() == target_id.lower():
                    # Garante que a classe pertence ao módulo importado e não é um import
                    if obj.__module__ == clean:
                        return obj
        except Exception:
            pass
        return None

    def _find_file_in_dir(self, directory: str, target_id: str) -> Optional[str]:
        norm = target_id.replace("_", "").lower()
        try:
            for fname in os.listdir(directory):
                if fname.endswith(".py") and not fname.startswith("__"):
                    if target_id.lower() in fname.lower() or norm in fname.lower().replace("_", ""):
                        return os.path.join(directory, fname)
        except OSError:
            pass
        return None
