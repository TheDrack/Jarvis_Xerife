# -*- coding: utf-8 -*-
import importlib
import inspect
import logging
import os
import pkgutil
from typing import Any, Dict, Optional, Type

logger = logging.getLogger(__name__)

class JarvisNexus:
    """
    Núcleo de Injeção de Dependências e Localização de Componentes.
    """
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self.dna: Dict[str, Any] = {}
        self._path_map: Dict[str, str] = {}

    def load_dna(self, dna_dict: dict):
        """Carrega a configuração do nexus_dna.yaml"""
        self.dna = dna_dict
        # Mapeia caminhos conhecidos para agilizar resoluções futuras
        components = dna_dict.get("components", {})
        for c_id, meta in components.items():
            if "hint_path" in meta:
                self._path_map[c_id] = meta["hint_path"]

    def resolve(self, target_id: str, hint_path: Optional[str] = None, **kwargs) -> Any:
        """
        Localiza, instancia e retorna um componente.
        Suporta 'hint_path' para evitar colisão de nomes.
        """
        # 1. Verificar cache de instâncias
        if target_id in self._instances:
            return self._instances[target_id]

        logger.info(f"🔍 [NEXUS] Resolvendo: '{target_id}'" + (f" (Hint: {hint_path})" if hint_path else ""))

        # 2. Tentar usar o hint_path (prioridade máxima)
        path_to_try = hint_path or self._path_map.get(target_id)
        if path_to_try:
            instance = self._instantiate_from_path(path_to_try, target_id)
            if instance:
                self._instances[target_id] = instance
                return instance

        # 3. Busca Global (Fallback) se o hint falhar ou não existir
        instance = self._global_search(target_id)
        if instance:
            self._instances[target_id] = instance
            return instance

        logger.error(f"❌ [NEXUS] Não foi possível localizar o componente: {target_id}")
        return None

    def _instantiate_from_path(self, module_path: str, target_id: str) -> Any:
        try:
            module = importlib.import_module(module_path)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Verifica se a classe é o alvo (case-insensitive)
                if name.lower() == target_id.replace("_", "").lower() or \
                   name.lower() == target_id.lower():
                    return obj()
        except Exception as e:
            logger.debug(f"Falha ao instanciar via hint {module_path}: {e}")
        return None

    def _global_search(self, target_id: str) -> Any:
        """Varredura recursiva em app para encontrar o componente."""
        for loader, module_name, is_pkg in pkgutil.walk_packages(['app'], 'app.'):
            if target_id in module_name:
                instance = self._instantiate_from_path(module_name, target_id)
                if instance:
                    logger.info(f"⚡ [NEXUS] '{target_id}' localizado em {module_name}")
                    return instance
        return None

# Instância Global
nexus = JarvisNexus()
