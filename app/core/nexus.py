# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import urllib.request
import threading
from typing import Any, Optional, Dict

# Configuração de logging integrada
logger = logging.getLogger(__name__)

class JarvisNexus:
    def __init__(self):
        # Define a raiz absoluta baseada na execução
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # Garante que a raiz do projeto esteja sempre no topo do path
        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)
            
        self._cache = self._load_remote_memory()

    def _load_remote_memory(self) -> dict:
        """Carrega o mapa de DNA para evitar varredura de disco repetitiva."""
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except:
            return {}

    def resolve(self, target_id: str, singleton: bool = True, hint_path: Optional[str] = None) -> Optional[Any]:
        """
        Buscador Dinâmico: Resolve o componente via Hint, Cache ou Varredura Global.
        """
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

        instance = None
        
        # 1. TENTATIVA VIA HINT PATH (Alta Prioridade)
        if hint_path:
            clean_hint = hint_path.replace("/", ".").replace("\\", ".").strip(".")
            # Tenta caminhos absolutos e relativos ao 'app'
            for path in [f"app.{clean_hint}.{target_id}", f"{clean_hint}.{target_id}"]:
                instance = self._instantiate(target_id, path)
                if instance: break

        # 2. TENTATIVA VIA CACHE/DNA (Evita I/O de disco)
        if not instance and target_id in self._cache:
            instance = self._instantiate(target_id, self._cache[target_id])

        # 3. DISCOVERY OMNISCIENTE (Busca física no repositório)
        if not instance:
            logger.info(f"🔍 [NEXUS] Iniciando Varredura Dinâmica para: '{target_id}'")
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
        """Varre o repositório buscando pelo arquivo correspondente."""
        target_file = f"{target_id}.py"
        for root, dirs, files in os.walk(self.base_dir):
            # Ignora pastas irrelevantes para performance
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'venv', '.venv', 'dist', 'build'}]
            
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                if rel_path == ".":
                    return target_id
                return f"{rel_path.replace(os.sep, '.')}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        """Importa o módulo e localiza a classe correta."""
        try:
            # Força o reload se o módulo já existir para garantir atualização de código em Cloud
            if module_path in sys.modules:
                module = importlib.reload(sys.modules[module_path])
            else:
                module = importlib.import_module(module_path)
            
            # Estratégia de busca de classe:
            # 1. PascalCase (drive_uploader -> DriveUploader)
            # 2. Nome idêntico ao arquivo
            # 3. Primeira classe que encontrar no módulo
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            
            clazz = getattr(module, class_name, None) or getattr(module, target_id, None)
            
            if not clazz:
                # Fallback: Varre o módulo por qualquer classe definida lá
                import inspect
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path:
                        clazz = obj
                        break

            if clazz:
                return clazz()
        except Exception as e:
            logger.debug(f"⚠️ [NEXUS] Falha ao instanciar {module_path}: {e}")
        return None

    def _update_dna(self, target_id: str, module_path: str):
        """Sincroniza o novo caminho encontrado com o Gist (Assíncrono)."""
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
