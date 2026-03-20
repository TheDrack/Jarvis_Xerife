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
    """Helper de descoberta flexível para ambientes Cloud e Local."""

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        cls, path = self._locate_class(target_id, hint_path)
        if not cls:
            return None
        return nexus_guarded_instantiate(cls)

    def _locate_class(self, target_id: str, hint_path: Optional[str] = None) -> Tuple[Optional[type], Optional[str]]:
        return self._global_search_with_path(target_id)

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[type], Optional[str]]:
        root_dir = os.getcwd()
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)

        search_root = os.path.join(root_dir, "app")
        if not os.path.exists(search_root):
            search_root = root_dir

        matches: List[Tuple[type, str]] = []
        # Normalização para comparação (remove underscores e coloca em lowercase)
        norm_target = target_id.lower().replace("_", "")

        for root, _, files in os.walk(search_root):
            if "__pycache__" in root or ".git" in root:
                continue
            
            for fname in files:
                if fname.endswith(".py") and not fname.startswith("__"):
                    # Se o nome do arquivo contém o target_id (ex: telegram_adapter.py contendo 'telegram')
                    # OU se o target_id está contido no nome do arquivo (ex: drive_uploader vs google_drive_uploader)
                    file_norm = fname.lower().replace("_", "")
                    if norm_target in file_norm or file_norm.replace(".py", "") in norm_target:
                        full_path = os.path.join(root, fname)
                        cls = self._find_class_from_path(full_path, target_id)
                        if cls:
                            matches.append((cls, full_path))

        if not matches:
            logger.error(f"❌ [NEXUS] Nenhum arquivo em '{search_root}' contém um match para '{target_id}'")
            return None, None
        
        # Priorização em caso de múltiplos matches
        if len(matches) > 1:
            for cls, path in matches:
                cls_name_low = cls.__name__.lower()
                # 1. Prioridade: Nome da classe bate com o ID (ex: TelegramAdapter == telegram_adapter)
                if cls_name_low == norm_target:
                    return cls, path
                # 2. Prioridade: ID é sufixo ou prefixo da classe (ex: GoogleDriveUploader contém drive_uploader)
                if norm_target in cls_name_low:
                    return cls, path
            return matches[0]

        return matches[0]

    def _find_class_from_path(self, file_path: str, target_id: str) -> Optional[type]:
        try:
            rel_path = os.path.relpath(file_path, os.getcwd())
            module_name = rel_path.replace(os.path.sep, ".").replace(".py", "")
            
            # Importa o módulo
            module = importlib.import_module(module_name)
            norm_target = target_id.lower().replace("_", "")
            
            for name, obj in inspect.getmembers(module, inspect.isclass):
                name_low = name.lower()
                
                # Match mais permissivo:
                # - Se o nome da classe normalizado for igual ao target normalizado
                # - OU se o target_id é uma parte fundamental do nome da classe
                if (name_low == norm_target or 
                    norm_target in name_low or 
                    name_low in norm_target):
                    
                    # Verificação de segurança: não instanciar classes base ou abstratas
                    if name.startswith("Base") or name.endswith("Mixin"):
                        continue
                        
                    return obj
        except Exception:
            pass
        return None
