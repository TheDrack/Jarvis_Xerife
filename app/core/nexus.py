# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import requests
from typing import Any, Optional
from threading import Lock

class JarvisNexus:
    def __init__(self):
        # A base_dir é a raiz absoluta do projeto (onde fica o .git, app/, data/, etc.)
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        self.gist_id = "23d15b3f9d010179ace501a79c78608f" 
        self._lock = Lock()
        
        # Sincronização inicial
        remote = self._load_remote_memory()
        self._cache = remote if remote else self._load_local_registry()
        self._instances = {}
        self._mutated = False

    def _load_local_registry(self) -> dict:
        registry_path = os.path.join(self.base_dir, "data", "nexus_registry.json")
        try:
            if not os.path.exists(registry_path): return {}
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {cid: path.rsplit(".", 1)[0] for cid, path in data.get("components", {}).items()}
        except: return {}

    def _load_remote_memory(self) -> dict:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200: return res.json()
        except: pass
        return {}

    def resolve(self, target_id: str, hint_path: Optional[str] = None, singleton: bool = True) -> Optional[Any]:
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        module_path = self._cache.get(target_id)
        instance = self._instantiate(target_id, module_path) if module_path else None

        if not instance:
            logging.warning(f"🔍 [NEXUS] '{target_id}' não encontrado no DNA. Iniciando VARREDURA TOTAL...")
            module_path = self._perform_omniscient_discovery(target_id)
            
            if module_path:
                logging.info(f"🎯 [NEXUS] Localizado em: {module_path}. Atualizando registros.")
                self._cache[target_id] = module_path
                self._mutated = True
                instance = self._instantiate(target_id, module_path)
                self.commit_memory() 
            else:
                logging.error(f"❌ [NEXUS] ERRO CRÍTICO: '{target_id}' não existe em NENHUMA pasta do projeto.")
                return None

        if singleton and instance:
            self._instances[target_id] = instance
        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        """
        VARREDURA OMNISCIENTE: Busca em TODAS as pastas do projeto, 
        sem exceção, partindo da raiz absoluta.
        """
        target_file = f"{target_id}.py"
        
        # Percorre absolutamente tudo a partir da base_dir
        for root, dirs, files in os.walk(self.base_dir):
            # Ignora apenas pastas de controle de versão e ambiente virtual
            if any(x in root for x in [".git", "__pycache__", "venv", ".frozen"]):
                continue
                
            if target_file in files:
                # Encontrou o arquivo físico. Agora gera o caminho de importação.
                full_path = os.path.join(root, target_id)
                rel_path = os.path.relpath(root, self.base_dir)
                
                # Se estiver na raiz, o rel_path será "."
                if rel_path == ".":
                    module_path = target_id
                else:
                    module_path = rel_path.replace(os.sep, ".") + f".{target_id}"
                
                return module_path
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            # Garante que o Python veja mudanças no disco
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])
            
            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            return clazz()
        except Exception as e:
            return None

    def commit_memory(self):
        if not self._mutated: return
        token = os.getenv("GIST_PAT")
        if not token: return
        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {"Authorization": f"token {token}"}
        payload = {"files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}}
        try:
            requests.patch(url, json=payload, headers=headers)
            self._mutated = False
        except: pass

nexus = JarvisNexus()
