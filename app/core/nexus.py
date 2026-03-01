# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import requests
import traceback
from typing import Any, Optional

class JarvisNexus:
    def __init__(self):
        # Base dir para o GitHub Actions
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
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
        
        if instance:
            logging.info(f"🧠 [NEXUS] '{target_id}' resolvido via DNA.")
            if singleton: self._instances[target_id] = instance
            return instance

        logging.info(f"🔍 [NEXUS] Buscando '{target_id}'...")

        if hint_path:
            hint_module = f"{hint_path.strip('/').replace('/', '.')}.{target_id}"
            logging.info(f"🔎 [NEXUS] Tentando Hint: {hint_module}")
            instance = self._instantiate(target_id, hint_module)
            if instance:
                self._update_dna(target_id, hint_module)
                if singleton: self._instances[target_id] = instance
                return instance

        # Varredura Global
        module_path = self._perform_omniscient_discovery(target_id)
        if module_path:
            logging.info(f"🎯 [NEXUS] LOCALIZADO: {module_path}. Tentando instanciar...")
            instance = self._instantiate(target_id, module_path)
            if instance:
                self._update_dna(target_id, module_path)
                if singleton: self._instances[target_id] = instance
                return instance
            else:
                logging.error(f"❌ [NEXUS] Arquivo encontrado em {module_path}, mas a INSTANCIAÇÃO falhou. Verifique o código do componente.")

        return None

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", ".frozen"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".": return target_id
                # Remove prefixo Jarvis_Xerife se o rel_path o incluir erroneamente
                clean_path = rel_path.replace("Jarvis_Xerife/", "").replace("Jarvis_Xerife", "")
                return f"{clean_path.strip('/').replace(os.sep, '.')}.{target_id}".lstrip(".")
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            if module_path in sys.modules: del sys.modules[module_path]
            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            return clazz()
        except Exception as e:
            # LOG CRÍTICO: Mostra por que o Python não conseguiu carregar o arquivo achado
            logging.debug(f"DEBUG: Falha ao carregar {module_path}: {str(e)}")
            return None

    def _update_dna(self, target_id: str, module_path: str):
        self._cache[target_id] = module_path
        token = os.getenv("GIST_PAT")
        if not token: return
        try:
            requests.patch(f"https://api.github.com/gists/{self.gist_id}", 
                json={"files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}},
                headers={"Authorization": f"token {token}"}, timeout=10)
        except: pass

nexus = JarvisNexus()
