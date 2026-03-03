# -*- coding: utf-8 -*-
import importlib
import inspect
import logging
import os
import pkgutil
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class JarvisNexus:
    """
    Núcleo de Injeção de Dependências com Auto-Cura.
    Hierarquia: Cache -> Hint -> Mapa Interno -> Busca Global.
    """
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self.dna: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}

    def load_dna(self, dna_dict: dict):
        """Carrega a configuração do nexus_dna.yaml"""
        self.dna = dna_dict
        components = dna_dict.get("components", {})
        for c_id, meta in components.items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        """
        Localiza e instancia um componente com prioridade de consulta.
        """
        # 1. Verificar Cache
        if target_id in self._instances:
            return self._instances[target_id]

        # 2. Tentar Hint Explícito (recebido na chamada)
        if hint_path:
            instance = self._instantiate_from_path(hint_path, target_id)
            if instance:
                self._instances[target_id] = instance
                return instance
            logger.warning(f"⚠️ [NEXUS] Hint explícito falhou para '{target_id}': {hint_path}")

        # 3. Consultar Mapa Interno (Carregado do DNA)
        stored_path = self._path_map.get(target_id)
        if stored_path and stored_path != hint_path:
            instance = self._instantiate_from_path(stored_path, target_id)
            if instance:
                self._instances[target_id] = instance
                return instance
            logger.warning(f"⚠️ [NEXUS] Caminho do mapa interno falhou para '{target_id}': {stored_path}")

        # 4. Busca Global (Cura) - Só ocorre se 2 e 3 falharem
        logger.info(f"🔍 [NEXUS] Iniciando varredura global para localizar '{target_id}'...")
        instance, real_path = self._global_search_with_path(target_id)
        
        if instance:
            # Alerta sobre a necessidade de correção no DNA/Chamada
            wrong_path = hint_path or stored_path
            if wrong_path:
                logger.error(
                    f"🚨 [NEXUS] CORREÇÃO: '{target_id}' não está em '{wrong_path}'. "
                    f"Achei em '{real_path}'. Atualize seu DNA."
                )
            else:
                logger.info(f"⚡ [NEXUS] '{target_id}' mapeado em '{real_path}'")

            # Atualiza o mapa para não precisar varrer de novo
            self._path_map[target_id] = real_path
            self._instances[target_id] = instance
            return instance

        logger.error(f"❌ [NEXUS] Falha total: '{target_id}' não localizado.")
        return None

    def _instantiate_from_path(self, module_path: str, target_id: str) -> Any:
        try:
            clean_path = module_path.replace("/", ".").replace(".py", "")
            module = importlib.import_module(clean_path)
            norm_target = target_id.replace("_", "").lower()

            for name, obj in inspect.getmembers(module, inspect.isclass):
                norm_class = name.replace("_", "").lower()
                if norm_class == norm_target or name.lower() == target_id.lower():
                    return obj()
        except Exception:
            return None
        return None

    def _global_search_with_path(self, target_id: str) -> Tuple[Optional[Any], Optional[str]]:
        for loader, module_name, is_pkg in pkgutil.walk_packages(['app'], 'app.'):
            # Procura pelo nome do componente no módulo
            if target_id.lower() in module_name.lower():
                instance = self._instantiate_from_path(module_name, target_id)
                if instance:
                    return instance, module_name
        return None, None

nexus = JarvisNexus()
