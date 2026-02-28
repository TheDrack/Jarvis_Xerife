# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import requests
from typing import Any, Optional
from threading import Lock

from app.core.nexuscomponent import NexusComponent

logging.basicConfig(
    level=logging.INFO,
    format="[NEXUS] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class JarvisNexus:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # ID do seu Gist de Backup
        self.gist_id = "23d15b3f9d010179ace501a79c78608f" 
        self._lock = Lock()
        self._cache = self._load_remote_memory() # Carrega do Gist
        self._instances = {}
        self._mutated = False # Flag para evitar writes desnecessários

    def _load_remote_memory(self) -> dict:
        """Tenta ler o mapa de componentes do Gist Raw."""
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                logging.info("📡 Memória remota sincronizada via Gist.")
                return res.json()
        except:
            logging.warning("⚠️ Falha ao acessar Gist. Usando discovery local.")
        return {}

    def commit_memory(self):
        """Persiste todas as novas descobertas no Gist em uma única chamada."""
        if not self._mutated:
            return

        token = os.getenv("GIST_PAT")
        if not token:
            logging.error("❌ GIST_PAT não encontrado. Memória não persistida.")
            return

        logging.info("💾 Persistindo mutações de DNA na memória remota...")
        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {"Authorization": f"token {token}"}
        payload = {
            "files": {
                "nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}
            }
        }
        try:
            res = requests.patch(url, json=payload, headers=headers)
            if res.status_code == 200:
                logging.info("✅ Memória Nexus atualizada no Gist.")
                self._mutated = False
        except Exception as e:
            logging.error(f"💥 Erro ao salvar memória: {e}")

    def resolve(self, target_id: str, hint_path: Optional[str] = None, singleton: bool = True) -> Optional[Any]:
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        module_path = self._cache.get(target_id)
        
        # Se não está no cache, faz discovery e marca como mutado
        if not module_path:
            module_path = self._perform_discovery(target_id, hint_path)
            if module_path:
                self._cache[target_id] = module_path
                self._mutated = True

        if not module_path:
            return None

        try:
            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            instance = clazz()
            
            if singleton:
                self._instances[target_id] = instance
            return instance
        except Exception as e:
            logging.error(f"FALHA NA CRISTALIZAÇÃO de '{target_id}': {e}")
            return None

    def _perform_discovery(self, target_id: str, hint: Optional[str]) -> Optional[str]:
        search_root = os.path.join(self.base_dir, "app", hint) if hint else os.path.join(self.base_dir, "app")
        filename = f"{target_id}.py"
        for root, _, files in os.walk(search_root):
            if filename in files:
                relative_path = os.path.relpath(root, self.base_dir)
                module_dots = relative_path.replace(os.sep, ".")
                return f"{module_dots}.{target_id}"
        return None

nexus = JarvisNexus()
