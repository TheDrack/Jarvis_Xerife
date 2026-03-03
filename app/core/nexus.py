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
        # 1. Configuração de Caminhos Absolutos
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)

        # 2. Configurações de Memória (Nuvem e Local)
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self.local_registry_path = os.path.join(self.base_dir, "data", "nexus_registry.json")
        
        # Garante que a pasta 'data' existe para o registro local
        os.makedirs(os.path.dirname(self.local_registry_path), exist_ok=True)

        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # Carrega a memória inicial (Gist > Local)
        self.discovery_cache = self._initialize_memory()

    def _initialize_memory(self) -> dict:
        """Sincroniza a memória global e local no boot."""
        gist_data = self._load_remote_gist()
        if gist_data:
            logger.info("🌐 [NEXUS] Memória sincronizada via Gist.")
            self._sync_to_local(gist_data)
            return gist_data
        
        local_data = self._load_local_registry()
        if local_data:
            logger.info("📂 [NEXUS] Usando registro local (Emergência/Dev).")
            return local_data
            
        return {}

    def _load_remote_gist(self) -> Optional[dict]:
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.warning(f"⚠️ Gist indisponível ou inacessível: {e}")
            return None

    def _load_local_registry(self) -> dict:
        if os.path.exists(self.local_registry_path):
            try:
                with open(self.local_registry_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Erro ao ler nexus_registry.json: {e}")
        return {}

    def _sync_to_local(self, data: dict):
        """Atualiza o JSON de visualização rápida do Dev para emergências."""
        try:
            with open(self.local_registry_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.debug(f"Falha ao espelhar memória para local: {e}")

    def resolve(self, target_id: str, singleton: bool = True) -> Optional[Any]:
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

        instance = None
        
        # 1. TENTA VIA MEMÓRIA (Gist/Local)
        if target_id in self.discovery_cache:
            path = self.discovery_cache[target_id]
            instance = self._instantiate(target_id, path)
            
            # Se o código mudou de lugar (path antigo falhou), limpa a memória
            if not instance:
                logger.warning(f"⚠️ [NEXUS] '{target_id}' não encontrado em {path}. Invalidando memória...")
                del self.discovery_cache[target_id]

        # 2. BUSCA GERAL (Deep Scan) - Ativado se a memória falhar ou não existir
        if not instance:
            logger.info(f"🔍 [NEXUS] Executando Busca Geral para: '{target_id}'")
            module_path = self._perform_omniscient_discovery(target_id)
            
            if module_path:
                instance = self._instantiate(target_id, module_path)
                if instance:
                    # Aprende o novo caminho e atualiza os registros
                    self.discovery_cache[target_id] = module_path
                    self._sync_to_local(self.discovery_cache)
                    logger.info(f"✅ [NEXUS] Novo caminho memorizado: {module_path}")

        if instance and singleton:
            with self._lock:
                self._instances[target_id] = instance

        return instance

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        """Varredura omnisciente do sistema de arquivos para auto-aprendizado."""
        target_file = f"{target_id}.py"
        for root, dirs, files in os.walk(self.base_dir):
            # Ignora pastas de sistema e dados para performance
            if any(x in root for x in [".git", "__pycache__", "venv", ".venv", "data"]):
                continue
            
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                import_path = rel_path.replace(os.sep, ".")
                return f"{import_path}.{target_id}" if rel_path != "." else target_id
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        """Importa dinamicamente e instancia o componente."""
        try:
            # Força recarregamento se necessário
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])
            
            module = importlib.import_module(module_path)
            
            # Tenta classe em PascalCase (ex: IntentProcessor) ou idêntica (intent_processor)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name, None) or getattr(module, target_id, None)
            
            if not clazz:
                # Fallback: primeira classe definida no arquivo
                import inspect
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_path:
                        clazz = obj
                        break
            
            if clazz:
                logger.info(f"⚡ [NEXUS] '{target_id}' instanciado via '{module_path}'")
                return clazz()
        except Exception:
            return None
        return None

nexus = JarvisNexus()
