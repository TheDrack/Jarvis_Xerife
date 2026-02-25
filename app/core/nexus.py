# -*- coding: utf-8 -*-

import importlib
import logging
import os
import json
import sys
from typing import Any, Optional
from threading import Lock

from app.core.nexuscomponent import NexusComponent

# Configuração de log para garantir visibilidade no GitHub Actions
logging.basicConfig(
    level=logging.INFO,
    format="[NEXUS] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class JarvisNexus:
    def __init__(self):
        # Localiza a raiz do projeto (onde está a pasta 'app')
        # Se este arquivo está em app/core/nexus.py, subimos dois níveis
        self.base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Memória persistente (JSON) para evitar redescobrimento
        self.memory_file = os.path.join(
            self.base_dir, "app", "core", "nexus_memory.json"
        )

        self._lock = Lock()
        self._cache = self._load_memory()   # Cache de caminhos (strings)
        self._instances = {}                # Cache de instâncias (Singletons)
        
        logging.info(f"Iniciado na raiz: {self.base_dir}")

    def _load_memory(self) -> dict:
        if not os.path.exists(self.memory_file):
            return {}
        try:
            with self._lock, open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Falha ao ler memória JSON: {e}")
            return {}

    def _save_memory(self) -> None:
        try:
            # Garante que o diretório existe antes de salvar
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with self._lock, open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=4)
        except Exception as e:
            logging.error(f"Falha ao salvar memória JSON: {e}")

    @staticmethod
    def _to_pascal_case(name: str) -> str:
        return "".join(word.capitalize() for word in name.split("_"))

    def resolve(
        self,
        target_id: str,
        hint_path: Optional[str] = None,
        singleton: bool = True
    ) -> Optional[Any]:

        logging.info(f"Resolvendo alvo: '{target_id}' (Hint: {hint_path})")

        # 1. Retorna instância viva se for singleton
        if singleton and target_id in self._instances:
            logging.info(f"Recuperando instância '{target_id}' do cache runtime.")
            return self._instances[target_id]

        # 2. Obtém path do cache ou faz discovery
        module_path = self._cache.get(target_id)

        if not module_path:
            module_path = self._perform_discovery(target_id, hint_path)
            if module_path:
                self._cache[target_id] = module_path
                self._save_memory()

        if not module_path:
            logging.error(f"ALVO NÃO ENCONTRADO: '{target_id}'")
            return None

        # 3. Importação dinâmica e Instanciação
        try:
            logging.info(f"Importando módulo: {module_path}")
            module = importlib.import_module(module_path)
            class_name = self._to_pascal_case(target_id)

            if not hasattr(module, class_name):
                raise AttributeError(f"Classe '{class_name}' não encontrada no módulo '{module_path}'")

            clazz = getattr(module, class_name)
            instance = clazz()

            if not isinstance(instance, NexusComponent):
                logging.warning(f"Aviso: '{class_name}' não herda de NexusComponent formalmente.")

            if singleton:
                self._instances[target_id] = instance

            logging.info(f"Sucesso ao cristalizar '{target_id}'")
            return instance

        except Exception as e:
            logging.error(f"FALHA NA CRISTALIZAÇÃO de '{target_id}': {e}")
            return None

    def _perform_discovery(
        self,
        target_id: str,
        hint: Optional[str]
    ) -> Optional[str]:
        
        # Define onde começar a busca. Se hint for 'infrastructure', busca em 'app/infrastructure'
        search_root = os.path.join(self.base_dir, "app", hint) if hint else os.path.join(self.base_dir, "app")
        
        logging.info(f"Iniciando discovery em: {search_root}")
        filename = f"{target_id}.py"

        for root, _, files in os.walk(search_root):
            if filename in files:
                # Converte o caminho do sistema operacional para o formato de importação python (ex: app.infrastructure.consolidator)
                relative_path = os.path.relpath(root, self.base_dir)
                module_dots = relative_path.replace(os.sep, ".")
                full_module_path = f"{module_dots}.{target_id}"
                
                logging.info(f"Discovery ENCONTROU: {full_module_path}")
                return full_module_path

        logging.warning(f"Discovery FALHOU para '{target_id}'")
        return None

# Instância global
nexus = JarvisNexus()
