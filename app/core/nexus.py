# -*- coding: utf-8 -*-
import importlib
import inspect
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class JarvisNexus:
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self.dna: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}

    def load_dna(self, dna_dict: dict):
        self.dna = dna_dict
        components = dna_dict.get("components", {})
        for c_id, meta in components.items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        if target_id in self._instances:
            return self._instances[target_id]

        # 1. Tentar Hint Explícito
        if hint_path:
            instance = self._instantiate_from_path(hint_path, target_id)
            if instance:
                self._instances[target_id] = instance
                return instance

        # 2. Consultar Mapa Interno (DNA)
        stored_path = self._path_map.get(target_id)
        if stored_path:
            instance = self._instantiate_from_path(stored_path, target_id)
            if instance:
                self._instances[target_id] = instance
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
            self._instances[target_id] = instance
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
