# -*- coding: utf-8 -*-
import importlib
import logging

logger = logging.getLogger("JarvisHub")

class JarvisHub:
    def __init__(self):
        self.sector_map = {
            "gears": "app.application.containers.gears_container",
            "models": "app.application.containers.models_container",
            "adapters": "app.application.containers.adapters_container",
            "capabilities": "app.application.containers.capabilities_container"
        }
        self._cache = {}

    def resolve(self, cap_id: str, sector: str):
        """ Importa o container do setor apenas quando necessário. """
        if cap_id in self._cache:
            return self._cache[cap_id]

        module_path = self.sector_map.get(sector)
        if not module_path:
            return None

        try:
            # Import dinâmico
            module = importlib.import_module(module_path)
            container_class = getattr(module, f"{sector.capitalize()}Container")
            container_instance = container_class()
            
            executor = container_instance.registry.get(cap_id)
            if executor:
                self._cache[cap_id] = executor
                return executor
        except Exception as e:
            logger.error(f"Erro ao resolver {cap_id} no setor {sector}: {e}")
        
        return None

# Instância Global Única
hub = JarvisHub()
