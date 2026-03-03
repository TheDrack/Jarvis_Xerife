# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import urllib.request
import threading
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

class JarvisNexus:
    def __init__(self):
        # 1. Configuração de Caminhos
        self.base_dir = os.path.abspath(os.getcwd())
        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)

        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self.local_registry_path = os.path.join(self.base_dir, "data", "nexus_registry.json")
        
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # Carrega a memória inicial (Gist > Local)
        self.discovery_cache = self._initialize_memory()

    def _initialize_memory(self) -> dict:
        """Sincroniza a memória global e local no boot."""
        gist_data = self._load_remote_gist()
        if gist_data:
            self._sync_to_local(gist_data)
            return gist_data
        return self._load_local_registry()

    def _load_remote_gist(self) -> Optional[dict]:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except: return None

    def _load_local_registry(self) -> dict:
        if os.path.exists(self.local_registry_path):
            try:
                with open(self.local_registry_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def _sync_to_local(self, data: dict):
        [span_0](start_span)"""Atualiza o JSON de visualização rápida do Dev[span_0](end_span)."""
        os.makedirs(os.path.dirname(self.local_registry_path), exist_ok=True)
        try:
            with open(self.local_registry_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except: pass

    def resolve(self, target_id: str, singleton: bool = True) -> Optional[Any]:
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

        instance = None
        
        # 1. TENTA VIA MEMÓRIA (Gist/Local)
        if target_id in self.discovery_cache:
            path = self.discovery_cache[target_id]
            instance = self._instantiate(target_id, path)
            
            # FALHA NA LOCALIZAÇÃO: Se o mapa mentiu, apaga a memória e força busca geral
            if not instance:
                logger.warning(f"⚠️ [NEXUS] '{target_id}' mudou de lugar. Invalidando memória...")
                del self.discovery_cache[target_id]

        # 2. BUSCA GERAL (Deep Scan) - Ativado se a memória falhar ou não existir
        if not instance:
            logger.info(f"🔍 [NEXUS] Executando Busca Geral para: '{target_id}'")
            module_path = self._perform_omniscient_discovery(target_id)
            
            if module_path:
                instance = self._instantiate(target_id, module_path)
                if instance:
                    # 3. ATUALIZAÇÃO DO MAPA: Aprende o novo caminho
                    self.discovery_cache[target_id] = module_path
                    self._sync_to_local(self.discovery_cache)
                    logger.info(f"✅ [NEXUS] Novo caminho memorizado: {module_path}")

        if instance and singleton:
            with self._lock:
                self._instances[target_id] = instance

        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        [span_1](start_span)"""Varredura total do sistema de arquivos[span_1](end_span)."""
        target_file = f"{target_id}.py"
        for root, dirs, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", "venv", "data"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                import_path = rel_path.replace(os.sep, ".")
                return f"{import_path}.{target_id}" if rel_path != "." else target_id
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        """Instanciação dinâmica com fallback de classe."""
        try:
            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name, None) or getattr(module, target_id, None)
            
            if not clazz:
                import inspect
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path:
                        clazz = obj; break
            return clazz() if clazz else None
        except: return None

nexus = JarvisNexus()
