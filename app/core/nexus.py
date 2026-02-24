# app/core/nexus.py

import importlib
import logging
import os
import json
from typing import Any, Optional

class JarvisNexus:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Raiz /app
        self.memory_file = os.path.join(self.base_dir, "core/nexus_memory.json")
        self._cache = self._load_memory()
        self._instances = {}

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_memory(self):
        with open(self.memory_file, 'w') as f:
            json.dump(self._cache, f, indent=4)

    def _to_pascal_case(self, name: str) -> str:
        return "".join(word.capitalize() for word in name.split("_"))

    def resolve(self, target_id: str, hint_path: str = None) -> Optional[Any]:
        """
        target_id: Nome do arquivo/classe (ex: 'llm_reasoning')
        hint_path: Opcional (ex: 'domain/gears')
        """
        # 1. Checa se já está instanciado
        if target_id in self._instances:
            return self._instances[target_id]

        # 2. Checa se já conhecemos o caminho (Memória)
        module_path = self._cache.get(target_id)
        
        # 3. Se não conhece ou se recebeu dica, busca no disco
        if not module_path:
            module_path = self._perform_discovery(target_id, hint_path)
            if module_path:
                self._cache[target_id] = module_path
                self._save_memory()

        if not module_path:
            logging.error(f"[NEXUS] Alvo '{target_id}' não encontrado em lugar nenhum.")
            return None

        # 4. Importação e Instanciação Dinâmica
        try:
            module = importlib.import_module(module_path)
            class_name = self._to_pascal_case(target_id)
            clazz = getattr(module, class_name)
            
            instance = clazz()
            self._instances[target_id] = instance
            return instance
        except Exception as e:
            logging.error(f"[NEXUS] Falha ao cristalizar '{target_id}': {e}")
            return None

    def _perform_discovery(self, target_id: str, hint: str) -> Optional[str]:
        """Varre o sistema para encontrar o arquivo correspondente ao target_id."""
        search_root = os.path.join(self.base_dir, hint) if hint else self.base_dir
        filename = f"{target_id}.py"

        for root, dirs, files in os.walk(search_root):
            if filename in files:
                # Converte o caminho do sistema em caminho de módulo python
                relative_path = os.path.relpath(os.path.join(root, target_id), self.base_dir)
                return "app." + relative_path.replace(os.sep, ".")
        return None

nexus = JarvisNexus()
