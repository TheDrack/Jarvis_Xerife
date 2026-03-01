# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import urllib.request
import urllib.parse
import traceback
from typing import Any, Optional

class JarvisNexus:
    def __init__(self):
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._cache = self._load_remote_memory()
        self._instances = {}

    def _load_remote_memory(self) -> dict:
        """Carrega a memória do Gist usando urllib (nativo) para evitar dependência do requests."""
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    # Limpeza de caminhos absolutos ou sujos do cache
                    return {k: v.split("Jarvis_Xerife.")[-1] for k, v in data.items()}
                return {}
        except Exception:
            return {}

    def resolve(self, target_id: str, hint_path: Optional[str] = None, singleton: bool = True) -> Optional[Any]:
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        module_path = self._cache.get(target_id)
        instance = self._instantiate(target_id, module_path) if module_path else None

        if instance:
            logging.info(f"🧠 [NEXUS] '{target_id}' resolvido via DNA.")
            if singleton: self._instances[target_id] = instance
            return instance

        # Busca Omnisciente
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
        """Localiza o arquivo e retorna o caminho de importação Python válido."""
        target_file = f"{target_id}.py"
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", ".frozen", "venv", ".venv"]): continue
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".": return target_id
                
                # Converte o caminho do SO (folder/sub) para notação Python (folder.sub)
                parts = rel_path.split(os.sep)
                if parts[0] == os.path.basename(self.base_dir):
                    parts = parts[1:]
                
                module_path = ".".join(parts)
                return f"{module_path}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])
            
            module = importlib.import_module(module_path)
            # Nome da Classe: snake_case -> PascalCase
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
        """Atualiza o Gist remotamente usando urllib (PATCH)."""
        self._cache[target_id] = module_path
        token = os.getenv("GIST_PAT")
        if not token: return
        
        url = f"https://api.github.com/gists/{self.gist_id}"
        payload = json.dumps({
            "files": {
                "nexus_memory.json": {
                    "content": json.dumps(self._cache, indent=4)
                }
            }
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=payload, method='PATCH')
        req.add_header("Authorization", f"token {token}")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logging.info(f"🧬 [NEXUS] DNA atualizado para '{target_id}'")
        except Exception as e:
            logging.warning(f"⚠️ [NEXUS] Falha ao sincronizar DNA: {e}")

nexus = JarvisNexus()
