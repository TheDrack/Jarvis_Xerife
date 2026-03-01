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
        # Raiz absoluta: garante que o os.walk veja tudo
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        
        # Carrega memória remota primeiro
        self._cache = self._load_remote_memory()
        self._instances = {}

    def _load_remote_memory(self) -> dict:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=10)
            return res.json() if res.status_code == 200 else {}
        except: return {}

    def resolve(self, target_id: str) -> Optional[Any]:
        if target_id in self._instances: return self._instances[target_id]

        module_path = self._cache.get(target_id)
        # Tenta instanciar pelo cache
        instance = self._instantiate(target_id, module_path) if module_path else None

        # Se falhar ou não houver no cache, busca física total
        if not instance:
            logging.info(f"🔍 [NEXUS] Varredura Omnisciente para: {target_id}")
            module_path = self._perform_omniscient_discovery(target_id)
            
            if module_path:
                instance = self._instantiate(target_id, module_path)
                if instance:
                    self._cache[target_id] = module_path
                    self._commit_to_gist()
            
        if instance:
            self._instances[target_id] = instance
        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", ".frozen"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                # Limpeza crítica: Remove o nome do repo ou pontos iniciais
                parts = rel_path.split(os.sep)
                if parts[0] in ["Jarvis_Xerife", "."]: parts = parts[1:]
                
                module_path = ".".join(parts) + f".{target_id}"
                return module_path.lstrip(".")
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            if module_path in sys.modules: del sys.modules[module_path]
            module = importlib.import_module(module_path)
            # Converte snake_case para PascalCase (drive_uploader -> DriveUploader)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            return clazz()
        except: return None

    def _commit_to_gist(self):
        token = os.getenv("GIST_PAT")
        if not token: return
        url = f"https://api.github.com/gists/{self.gist_id}"
        payload = {"files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}}
        try:
            requests.patch(url, json=payload, headers={"Authorization": f"token {token}"})
        except: pass

nexus = JarvisNexus()
