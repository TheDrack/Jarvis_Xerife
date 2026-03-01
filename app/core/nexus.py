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
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._cache = self._load_remote_memory()
        self._instances = {}

    def _load_remote_memory(self) -> dict:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                # Limpeza de cache sujo que contenha o prefixo do diretório do runner
                return {k: v.split("Jarvis_Xerife.")[-1] for k, v in data.items()}
            return {}
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

        logging.info(f"🔍 [NEXUS] Buscando '{target_id}' em todo o projeto...")
        module_path = self._perform_omniscient_discovery(target_id)

        if module_path:
            logging.info(f"🎯 [NEXUS] LOCALIZADO: {module_path}. Tentando instanciar...")
            instance = self._instantiate(target_id, module_path)
            if instance:
                self._update_dna(target_id, module_path)
                if singleton: self._instances[target_id] = instance
                return instance

        return None

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", ".frozen", "venv"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".": return target_id

                # Transforma o caminho do SO em caminho de módulo Python (ex: app/core -> app.core)
                parts = rel_path.split(os.sep)
                # Filtra se por acaso o caminho começar com o nome da pasta raiz
                if parts[0] == os.path.basename(self.base_dir):
                    parts = parts[1:]

                module_path = ".".join(parts)
                return f"{module_path}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            # Garante que o módulo seja recarregado se necessário
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])

            module = importlib.import_module(module_path)
            # Converte snake_case para PascalCase (ex: drive_uploader -> DriveUploader)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))

            if not hasattr(module, class_name):
                logging.error(f"❌ [NEXUS] Classe {class_name} não existe em {module_path}")
                return None

            clazz = getattr(module, class_name)
            return clazz()
        except Exception:
            logging.error(f"💥 [NEXUS] Erro crítico ao instanciar {module_path}:")
            logging.error(traceback.format_exc())
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
