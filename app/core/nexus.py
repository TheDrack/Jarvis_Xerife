import importlib
import logging
import os
import json
from typing import Any, Optional
from threading import Lock



class JarvisNexus:
    def __init__(self):
        # Raiz /app
        self.base_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        # Memória persistente (JSON por enquanto)
        self.memory_file = os.path.join(
            self.base_dir, "core/nexus_memory.json"
        )

        self._lock = Lock()
        self._cache = self._load_memory()   # Cache persistente (paths)
        self._instances = {}                # Cache runtime (singletons)

    # ==========================
    # Memória Persistente
    # ==========================

    def _load_memory(self) -> dict:
        if not os.path.exists(self.memory_file):
            return {}

        try:
            with self._lock, open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[NEXUS] Falha ao ler memória JSON: {e}")
            return {}

    def _save_memory(self) -> None:
        try:
            with self._lock, open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=4)
        except Exception as e:
            logging.error(f"[NEXUS] Falha ao salvar memória JSON: {e}")

    # ==========================
    # Utilitários
    # ==========================

    @staticmethod
    def _to_pascal_case(name: str) -> str:
        return "".join(word.capitalize() for word in name.split("_"))

    # ==========================
    # API Principal
    # ==========================

    def resolve(
        self,
        target_id: str,
        hint_path: Optional[str] = None,
        singleton: bool = True
    ) -> Optional[Any]:
        """
        Resolve e cristaliza um componente pelo ID lógico.

        target_id : nome do arquivo/classe (ex: 'llm_reasoning')
        hint_path : caminho opcional para restringir discovery
        singleton : controla cache de instância
        """

        # 1️⃣ Retorna instância viva se existir
        if singleton and target_id in self._instances:
            return self._instances[target_id]

        # 2️⃣ Obtém path conhecido
        module_path = self._cache.get(target_id)

        # 3️⃣ Discovery se necessário
        if not module_path:
            module_path = self._perform_discovery(target_id, hint_path)

            if module_path:
                self._cache[target_id] = module_path
                self._save_memory()

        if not module_path:
            logging.error(f"[NEXUS] Alvo '{target_id}' não encontrado.")
            return None

        # 4️⃣ Importação e cristalização
        try:
            module = importlib.import_module(module_path)
            class_name = self._to_pascal_case(target_id)

            if not hasattr(module, class_name):
                raise AttributeError(
                    f"Classe '{class_name}' não encontrada em '{module_path}'"
                )

            clazz = getattr(module, class_name)
            instance = clazz()

            if not isinstance(instance, NexusComponent):
                raise TypeError(
                    f"'{class_name}' não implementa NexusComponent"
                )

            if singleton:
                self._instances[target_id] = instance

            return instance

        except Exception as e:
            logging.error(f"[NEXUS] Falha ao cristalizar '{target_id}': {e}")
            return None

    # ==========================
    # Discovery Dinâmico
    # ==========================

    def _perform_discovery(
        self,
        target_id: str,
        hint: Optional[str]
    ) -> Optional[str]:
        """
        Varre o sistema para localizar o módulo correspondente ao target_id.
        """

        search_root = (
            os.path.join(self.base_dir, hint)
            if hint else self.base_dir
        )

        filename = f"{target_id}.py"

        for root, _, files in os.walk(search_root):
            if filename in files:
                relative_path = os.path.relpath(
                    os.path.join(root, target_id),
                    self.base_dir
                )
                return "app." + relative_path.replace(os.sep, ".")

        return None


# Instância canônica do Nexus
nexus = JarvisNexus()