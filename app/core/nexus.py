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
        # Força o diretório base absoluto
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not self.base_dir in sys.path:
            sys.path.insert(0, self.base_dir)
            
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
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
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

        instance = None
        
        # 1. TENTA CAMINHOS CONHECIDOS (Fast Track para evitar OS.WALK)
        standard_paths = [
            f"app.application.services.{target_id}",
            f"app.adapters.infrastructure.{target_id}",
            f"app.core.{target_id}",
            f"capabilities.{target_id}"
        ]
        
        for path in standard_paths:
            instance = self._instantiate(target_id, path)
            if instance: break

        # 2. DISCOVERY OMNISCIENTE (Se falhar nos conhecidos)
        if not instance:
            logger.info(f"🔍 [NEXUS] Discovery profundo para: '{target_id}' em {self.base_dir}")
            module_path = self._perform_omniscient_discovery(target_id)
            if module_path:
                instance = self._instantiate(target_id, module_path)

        if instance and singleton:
            with self._lock:
                self._instances[target_id] = instance
        
        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        target_file = f"{target_id}.py"
        # Varre a partir da raiz do projeto
        for root, dirs, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", "venv", ".venv"]): continue
            
            if target_file in files:
                # Converte o caminho do sistema de arquivos para o formato de import do Python
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".":
                    return target_id
                
                # Limpa o caminho para garantir compatibilidade com Linux/Windows no Render
                import_path = rel_path.replace(os.sep, ".")
                return f"{import_path}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        try:
            # Tenta importar
            module = importlib.import_module(module_path)
            
            # Estratégia de nome de classe: PascalCase ou idêntico
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            
            # Busca a classe no módulo
            clazz = getattr(module, class_name, None) or getattr(module, target_id, None)
            
            if not clazz:
                # Último recurso: pega a primeira classe definida no arquivo que não seja importada
                import inspect
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path:
                        clazz = obj
                        break

            if clazz:
                logger.info(f"✅ [NEXUS] '{target_id}' instanciado via '{module_path}'")
                return clazz()
        except:
            return None
        return None

nexus = JarvisNexus()
