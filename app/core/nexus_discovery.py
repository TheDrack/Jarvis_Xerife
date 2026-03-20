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
    """Helper de descoberta ultra-flexível para ambientes Cloud, CI/CD e Local."""

    def _resolve_internal(self, target_id: str, hint_path: Optional[str] = None) -> Any:
        cls, path = self._locate_class(target_id, hint_path)
        if not cls:
            return None
        return nexus_guarded_instantiate(cls)

    def _locate_class(self, target_id: str, hint_path: Optional[str] = None) -> Tuple[Optional[type], Optional[str]]:
        return self._global_search_with_path(target_id)

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[type], Optional[str]]:
        # Força a raiz do projeto no PYTHONPATH
        current_dir = os.path.abspath(os.getcwd())
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        # Localiza a pasta 'app' independentemente de onde o script foi chamado
        search_root = os.path.join(current_dir, "app")
        if not os.path.exists(search_root):
            # Se não achar /app no CWD, tenta subir um nível (fallback para execução interna)
            potential_root = os.path.dirname(os.path.abspath(__file__))
            while "app" not in os.listdir(potential_root) and potential_root != "/":
                potential_root = os.path.dirname(potential_root)
            search_root = os.path.join(potential_root, "app")

        matches: List[Tuple[type, str]] = []
        # Normalização agressiva: remove prefixos/sufixos comuns e underscores
        norm_target = target_id.lower().replace("_", "").replace("adapter", "").replace("service", "").replace("uploader", "").replace("backup", "")

        for root, _, files in os.walk(search_root):
            if "__pycache__" in root or ".git" in root:
                continue
            
            for fname in files:
                if fname.endswith(".py") and not fname.startswith("__"):
                    file_norm = fname.lower().replace("_", "")
                    
                    # Match Heurístico Expandido:
                    # Se o 'core' do nome do arquivo bater com o 'core' do target_id
                    if norm_target in file_norm or file_norm.replace(".py", "") in norm_target:
                        full_path = os.path.join(root, fname)
                        cls = self._find_class_from_path(full_path, target_id)
                        if cls:
                            matches.append((cls, full_path))

        if not matches:
            logger.error(f"❌ [NEXUS] Nenhum arquivo em '{search_root}' contém um match para '{target_id}'")
            return None, None
        
        if len(matches) > 1:
            # Prioridade absoluta: Nome da classe contém o target_id
            target_clean = target_id.lower().replace("_", "")
            for cls, path in matches:
                if target_clean in cls.__name__.lower():
                    return cls, path
            return matches[0]

        return matches[0]

    def _find_class_from_path(self, file_path: str, target_id: str) -> Optional[type]:
        try:
            # Converte path absoluto para path de módulo
            # Garante que o split seja feito corretamente em Windows ou Linux
            parts = os.path.normpath(file_path).split(os.sep)
            try:
                app_idx = parts.index("app")
                module_parts = parts[app_idx:]
                module_name = ".".join(module_parts).replace(".py", "")
            except ValueError:
                return None

            module = importlib.import_module(module_name)
            
            # Normalização para busca de classe
            norm_target = target_id.lower().replace("_", "").replace("adapter", "").replace("uploader", "")
            
            for name, obj in inspect.getmembers(module, inspect.isclass):
                name_low = name.lower()
                
                # Regras de Aceitação de Classe:
                # 1. Nome da classe contém o núcleo do target_id
                # 2. Ignora Mixins e classes abstratas
                if (norm_target in name_low or name_low in norm_target):
                    if not (name.endswith("Mixin") or name.startswith("Base")):
                        return obj
        except Exception:
            pass
        return None
