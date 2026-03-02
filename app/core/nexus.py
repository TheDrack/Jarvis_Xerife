# -*- coding: utf-8 -*-
import importlib
import logging
import os
import json
import sys
import urllib.request
import urllib.parse
import traceback
import threading
from typing import Any, Optional, Dict

# Configuração de logging
logger = logging.getLogger(__name__)

class CloudMock:
    """Objeto dinâmico que aceita qualquer chamada de método para evitar quebras em Cloud."""
    def __init__(self, target_id: str):
        self._target_id = target_id

    def __getattr__(self, name):
        def method(*args, **kwargs):
            # Log apenas em DEBUG para não poluir o Render
            logging.debug(f"☁️ [NEXUS-MOCK] {self._target_id}.{name} chamado em Cloud.")
            return None
        return method
    
    def __bool__(self):
        return False # Permite verificações 'if not adapter'

class JarvisNexus:
    def __init__(self):
        self.base_dir = os.path.abspath(os.getcwd())
        self.gist_id = "23d15b3f9d010179ace501a79c78608f"
        self._instances: Dict[str, Any] = {}
        self._resolving: set = set() # Proteção contra recursão infinita
        self._lock = threading.Lock()
        
        # Detecta ambiente Cloud
        self.is_cloud = os.getenv("RENDER") == "true" or not sys.stdin.isatty()
        
        # Cache inicial
        self._cache = self._load_remote_memory()

    def _load_remote_memory(self) -> dict:
        """Carrega o DNA do Gist com tratamento de erro robusto."""
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            # Bypass cache do urllib para garantir DNA atualizado
            req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=7) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    # Normaliza caminhos (remove prefixos legados se houver)
                    return {k: v.split("Jarvis_Xerife.")[-1] for k, v in data.items()}
        except Exception as e:
            logger.warning(f"⚠️ [NEXUS] DNA remoto indisponível: {e}. Usando descoberta local.")
        return {}

    def resolve(self, target_id: str, singleton: bool = True) -> Optional[Any]:
        """Resolve uma dependência garantindo thread-safety e evitando loops."""
        with self._lock:
            if singleton and target_id in self._instances:
                return self._instances[target_id]

            # Proteção contra loop: se já estamos tentando resolver este ID, aborte
            if target_id in self._resolving:
                logger.error(f"🔄 [NEXUS] Loop de dependência detectado para '{target_id}'!")
                return None
            
            self._resolving.add(target_id)

        try:
            instance = None
            module_path = self._cache.get(target_id)

            if module_path:
                instance = self._instantiate(target_id, module_path)

            if not instance:
                logger.info(f"🔍 [NEXUS] Buscando '{target_id}' via Omniscient Discovery...")
                module_path = self._perform_omniscient_discovery(target_id)
                if module_path:
                    instance = self._instantiate(target_id, module_path)
                    if instance:
                        self._update_dna(target_id, module_path)

            if instance and singleton:
                with self._lock:
                    self._instances[target_id] = instance
            
            return instance

        finally:
            with self._lock:
                self._resolving.discard(target_id)

    def _perform_omniscient_discovery(self, target_id: str) -> Optional[str]:
        """Localiza o arquivo no projeto e converte para path de módulo Python."""
        target_file = f"{target_id}.py"
        for root, _, files in os.walk(self.base_dir):
            if any(x in root for x in [".git", "__pycache__", "venv", ".venv", "tests"]):
                continue
            
            if target_file in files:
                rel_path = os.path.relpath(root, self.base_dir)
                # Converte caminho de diretório para notação de pacote Python
                if rel_path == ".":
                    return target_id
                
                package_path = rel_path.replace(os.sep, ".")
                return f"{package_path}.{target_id}"
        return None

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        """Cria a instância da classe, tratando desvios de Hardware em Cloud."""
        
        # Protocolo de Simbiose: Bloqueio de hardware local em nuvem
        hardware_keywords = ["keyboard", "audio", "camera", "gpio", "edge_adapter"]
        if self.is_cloud and any(key in target_id or key in module_path for key in hardware_keywords):
            logger.info(f"🛡️ [NEXUS] Hardware Bypass: '{target_id}' -> CloudMock.")
            return CloudMock(target_id)

        try:
            # Garante que o sys.path contenha o base_dir
            if self.base_dir not in sys.path:
                sys.path.insert(0, self.base_dir)

            module = importlib.import_module(module_path)
            # CamelCase: telegram_adapter -> TelegramAdapter
            class_name = "".join(word.capitalize() for word in target_id.split("_"))

            if not hasattr(module, class_name):
                logger.error(f"❌ [NEXUS] Classe '{class_name}' não encontrada em {module_path}")
                return None

            clazz = getattr(module, class_name)
            return clazz()

        except ImportError as e:
            if self.is_cloud:
                logger.warning(f"⚠️ [NEXUS] Dependência '{e.name}' ausente em Cloud. Mockando {target_id}.")
                return CloudMock(target_id)
            logger.error(f"❌ [NEXUS] Erro de importação em {module_path}: {e}")
            return None
        except Exception:
            logger.error(f"💥 [NEXUS] Erro crítico ao instanciar {target_id}:\n{traceback.format_exc()}")
            return None

    def _update_dna(self, target_id: str, module_path: str):
        """Sincroniza o novo caminho com o Gist remoto."""
        self._cache[target_id] = module_path
        token = os.getenv("GIST_PAT")
        if not token or not self.gist_id:
            return

        def _async_update():
            try:
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
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"🧬 [NEXUS] DNA atualizado: '{target_id}'")
            except Exception as e:
                logger.warning(f"⚠️ [NEXUS] Erro ao sincronizar DNA Gist: {e}")

        # Atualiza em background para não travar a resolução principal
        threading.Thread(target=_async_update, daemon=True).start()

# Instância Global Única
nexus = JarvisNexus()
