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
        self.gist_id = "23d15b3f9d010179ace501a79c78608f" 
        self._lock = Lock()

        # Prioridade: Gist (Remote Memory) -> Se falhar, tenta Local
        remote = self._load_remote_memory()
        if remote:
            self._cache = remote
            logging.info("🧠 Memória Nexus sincronizada via Gist (Prioridade Máxima).")
        else:
            self._cache = self._load_local_registry()
            logging.warning("⚠️ Gist inacessível. Usando registro local como fallback.")

        self._instances = {}
        self._mutated = False

    def _load_local_registry(self) -> dict:
        """Lê o nexus_registry.json apenas para carga inicial se o Gist falhar."""
        registry_path = os.path.join(self.base_dir, "data", "nexus_registry.json")
        try:
            if not os.path.exists(registry_path): return {}
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            components = data.get("components", {})
            cache = {}
            for cid, full_path in components.items():
                parts = full_path.rsplit(".", 1)
                cache[cid] = parts[0] if len(parts) == 2 else full_path
            return cache
        except Exception:
            return {}

    def _load_remote_memory(self) -> dict:
        """Tenta ler o mapa de componentes do Gist Raw."""
        url = f"https://gist.githubusercontent.com/TheDrack/{self.gist_id}/raw/nexus_memory.json"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                return res.json()
        except:
            pass
        return {}

    def _update_local_visual_registry(self):
        """Atualiza o JSON local apenas para visualização do usuário."""
        registry_path = os.path.join(self.base_dir, "data", "nexus_registry.json")
        os.makedirs(os.path.dirname(registry_path), exist_ok=True)
        components = {}
        for cid, module_path in self._cache.items():
            class_name = "".join(word.capitalize() for word in cid.split("_"))
            components[cid] = f"{module_path}.{class_name}"

        data = {
            "info": "Este arquivo é apenas para visualização local. A verdade reside no Gist.",
            "components": components
        }
        try:
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"❌ Falha ao atualizar visual local: {e}")

    def commit_memory(self):
        """Persiste mutações no Gist e atualiza o visual local."""
        if not self._mutated:
            return

        token = os.getenv("GIST_PAT")
        if not token:
            logging.error("❌ GIST_PAT ausente. Impossível persistir mutação de DNA.")
            return

        url = f"https://api.github.com/gists/{self.gist_id}"
        headers = {"Authorization": f"token {token}"}
        payload = {"files": {"nexus_memory.json": {"content": json.dumps(self._cache, indent=4)}}}

        try:
            res = requests.patch(url, json=payload, headers=headers)
            if res.status_code == 200:
                logging.info("✅ DNA Nexus atualizado no Gist.")
                self._update_local_visual_registry()
                self._mutated = False
        except Exception as e:
            logging.error(f"💥 Erro no commit remoto: {e}")

    def resolve(self, target_id: str, hint_path: Optional[str] = None, singleton: bool = True) -> Optional[Any]:
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        module_path = self._cache.get(target_id)
        instance = None

        # Tenta carregar do cache existente
        if module_path:
            instance = self._instantiate(target_id, module_path)

        # Se não encontrou ou o caminho no cache estava defasado (ImportError)
        if not instance:
            logging.info(f"🔍 '{target_id}' não encontrado ou defasado. Iniciando busca exaustiva...")
            module_path = self._perform_discovery(target_id, hint_path)

            if module_path:
                logging.info(f"✨ Localizado: {module_path}. Atualizando registros...")
                self._cache[target_id] = module_path
                self._mutated = True
                instance = self._instantiate(target_id, module_path)
                # Salva imediatamente para evitar perdas
                self.commit_memory() 
            else:
                logging.error(f"❌ CRITICAL: Componente '{target_id}' não existe no repositório.")
                return None

        if singleton and instance:
            self._instances[target_id] = instance
        return instance

    def _instantiate(self, target_id: str, module_path: str) -> Optional[Any]:
        """Tenta importar e instanciar, retorna None se o arquivo mudou de lugar."""
        try:
            # Força o reload para garantir que não estamos pegando cache de importação antigo
            if module_path in sys.modules:
                importlib.reload(sys.modules[module_path])

            module = importlib.import_module(module_path)
            class_name = "".join(word.capitalize() for word in target_id.split("_"))
            clazz = getattr(module, class_name)
            return clazz()
        except (ImportError, ModuleNotFoundError, AttributeError):
            return None

    def _perform_discovery(self, target_id: str, hint: Optional[str]) -> Optional[str]:
        filename = f"{target_id}.py"

        # 1. Busca com Hint
        if hint:
            logging.info(f"🔎 Buscando com hint em 'app/{hint}'...")
            path = self._search_in_folder(os.path.join(self.base_dir, "app", hint), filename)
            if path: return path

        # 2. Se não encontrou no hint, avisa e busca no repositório inteiro (app/)
        logging.warning(f"⚠️ Não encontrado via Hint. Varrendo repositório completo...")
        return self._search_in_folder(os.path.join(self.base_dir, "app"), filename)

    def _search_in_folder(self, start_dir: str, filename: str) -> Optional[str]:
        if not os.path.exists(start_dir): return None

        for root, _, files in os.walk(start_dir):
            if filename in files:
                relative_path = os.path.relpath(root, self.base_dir)
                module_dots = relative_path.replace(os.sep, ".")
                return f"{module_dots}.{filename[:-3]}"
        return None

nexus = JarvisNexus()
