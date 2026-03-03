# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import urllib.request
import threading
import traceback
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

class JarvisNexus:
    def __init__(self):
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.is_cloud = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("RENDER") == "true"
        self._cache = self._load_remote_memory()

    def _load_remote_memory(self) -> dict:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except:
            return {}

    def resolve(self, target_id: str, singleton: bool = True, hint_path: Optional[str] = None) -> Optional[Any]:
        """
        Resolve o componente priorizando o hint_path fornecido pelo Pipeline.
        """
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

        instance = None
        
        # 1. TENTATIVA VIA HINT PATH (ALTA PRIORIDADE)
        if hint_path:
            # Normaliza: adapters/infrastructure -> app.adapters.infrastructure.target_id
            clean_hint = hint_path.replace("/", ".").replace("\\", ".").strip(".")
            # Tenta com prefixo 'app.' e sem ele
            potential_paths = [
                f"app.{clean_hint}.{target_id}",
                f"{clean_hint}.{target_id}"
            ]
            
            for path in potential_paths:
                instance = self._instantiate(target_id, path)
                if instance:
                    logger.info(f"📍 [NEXUS] '{target_id}' resolvido via Hint: {path}")
                    break

        # 2. TENTATIVA VIA CACHE/DNA
        if not instance and target_id in self._cache:
            instance = self._instantiate(target_id, self._cache[target_id])

        # 3. TENTATIVA VIA DISCOVERY (ULTIMO RECURSO)
        if not instance:
            logger.info(f"🔍 [NEXUS] Hint falhou ou ausente. Iniciando Discovery para '{target_id}'...")
            module_path = self._perform_omniscient_discovery(target_id)
            if module_path:
                instance = self._instantiate(target_id, module_path)
                if instance:
                    self._update_dna(target_id, module_path)

        if instance and singleton:
            with self._lock:
                self._instances[target_id] = instance
        
        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        for root, dirs, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", "venv", ".venv"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".": return target_id
                return f"{rel_path.replace(os.sep, '.')}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            # Garante que o diretório base está no path
            if self.base_dir not in sys.path:
                sys.path.insert(0, self.base_dir)
            
            module = importlib.import_module(module_path)
            # Tenta converter snake_case para PascalCase (drive_uploader -> DriveUploader)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            
            clazz = getattr(module, class_name, None) or getattr(module, target_id, None)
            
            if clazz:
                return clazz()
            return None
        except Exception:
            return None

    def _update_dna(self, target_id: str, module_path: str):
        self._cache[target_id] = module_path
        token = os.getenv("GIST_PAT")
        if not token: return
        
        def _async_update():
            try:
                url = f"https://api.github.com/gists/{self.gist_id}"
                payload = json.dumps({
                    "files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}
                }).encode('utf-8')
                req = urllib.request.Request(url, data=payload, method='PATCH')
                req.add_header("Authorization", f"token {token}")
                req.add_header("Content-Type", "application/json")
                urllib.request.urlopen(req, timeout=10)
            except: pass
            
        threading.Thread(target=_async_update, daemon=True).start()

nexus = JarvisNexus()
