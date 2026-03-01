# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import requests
from typing import Any, Optional

class JarvisNexus:
    def __init__(self):
        # Base dir absoluta
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        
        # Sincronização
        self._cache = self._load_remote_memory()
        self._instances = {}

    def _load_remote_memory(self) -> dict:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=5)
            return res.json() if res.status_code == 200 else {}
        except: return {}

    def resolve(self, target_id: str, hint_path: Optional[str] = None, singleton: bool = True) -> Optional[Any]:
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        module_path = self._cache.get(target_id)
        instance = self._instantiate(target_id, module_path) if module_path else None

        if not instance:
            logging.info(f"🔍 [NEXUS] '{target_id}' não mapeado. Iniciando busca exaustiva...")
            module_path = self._perform_discovery(target_id)
            
            if module_path:
                self._cache[target_id] = module_path
                self.commit_memory() # Salva no Gist para a próxima rodada
                instance = self._instantiate(target_id, module_path)
            
        if instance and singleton:
            self._instances[target_id] = instance
        return instance

    def _perform_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        # Varredura completa no repositório
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", ".frozen"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".":
                    return target_id
                return rel_path.replace(os.sep, ".") + f".{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            if module_path in sys.modules: del sys.modules[module_path]
            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            return clazz()
        except: return None

    def commit_memory(self):
        token = os.getenv("GIST_PAT")
        if not token: return
        url = f"https://api.github.com/gists/{self.gist_id}"
        payload = {"files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}}
        try:
            requests.patch(url, json=payload, headers={"Authorization": f"token {token}"}, timeout=10)
        except: pass

nexus = JarvisNexus()
