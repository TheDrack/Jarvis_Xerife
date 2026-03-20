# -*- coding: utf-8 -*-
import importlib
import inspect
import logging
import os
import sys
from typing import Any, List, Optional, Tuple

from app.core.nexus_exceptions import (
    NEXUS_IMPORT_TIMEOUT,
    NEXUS_STRICT_MODE,
    AmbiguousComponentError,
    ImportTimeoutError,
    nexus_guarded_instantiate
)

logger = logging.getLogger(__name__)

class _NexusDiscoveryMixin:
    """Helper de descoberta otimizado para ambientes Cloud (Render/Docker)."""

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        cls, path = self._locate_class(target_id, hint_path)
        if not cls:
            return None
        return nexus_guarded_instantiate(cls)

    def _locate_class(self, target_id: str, hint_path: Optional[str] = None) -> Tuple[Optional[type], Optional[str]]:
        # 1. Busca Global
        return self._global_search_with_path(target_id)

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[type], Optional[str]]:
        # Garante que a raiz do projeto está no sys.path para imports relativos
        root_dir = os.getcwd()
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        # No Render, buscamos a partir de 'app'
        search_root = os.path.join(root_dir, "app")
        if not os.path.exists(search_root):
            search_root = root_dir

        matches: List[Tuple[type, str]] = []
        # Normalização para match (ex: assistant_service -> assistantservice)
        norm_target = target_id.replace("_", "").lower()

        for root, _, files in os.walk(search_root):
            if "__pycache__" in root or ".git" in root:
                continue
            
            for fname in files:
                if fname.endswith(".py") and not fname.startswith("__"):
                    full_path = os.path.join(root, fname)
                    
                    # Tenta encontrar a classe dentro deste arquivo
                    cls = self._find_class_from_path(full_path, target_id)
                    if cls:
                        matches.append((cls, full_path))

        if not matches:
            logger.error(f"❌ [NEXUS] Nenhum arquivo em '{search_root}' contém um match para '{target_id}'")
            return None, None
        
        # Se houver mais de um, tenta o nome mais próximo
        if len(matches) > 1:
            for cls, path in matches:
                if cls.__name__.lower() == target_id.lower().replace("_", ""):
                    return cls, path
            return matches[0] # Fallback para o primeiro

        return matches[0]

    def _find_class_from_path(self, file_path: str, target_id: str) -> Optional[type]:
        try:
            # Converte path absoluto em path de módulo python
            # Ex: /opt/render/project/src/app/core/nexus.py -> app.core.nexus
            rel_path = os.path.relpath(file_path, os.getcwd())
            module_name = rel_path.replace(os.path.sep, ".").replace(".py", "")
            
            # Importa o módulo dinamicamente
            module = importlib.import_module(module_name)
            
            norm_target = target_id.replace("_", "").lower()
            
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Critérios de Match:
                # 1. Nome exato (TelegramAdapter == telegram_adapter)
                # 2. Nome contido (SQLiteHistoryAdapter contém 'database' ou 'history')
                name_low = name.lower()
                
                # Match especial para Database/Adapter
                is_db_match = (target_id == "database_adapter" and "adapter" in name_low and ("sqlite" in name_low or "postgres" in name_low or "history" in name_low))
                
                if name_low == norm_target or name_low == target_id.replace("_", "") or is_db_match:
                    # Verifica se a classe foi definida no módulo (evita imports)
                    if obj.__module__ == module_name:
                        return obj
        except Exception:
            pass
        return None
