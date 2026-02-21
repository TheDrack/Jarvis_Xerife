# app/application/containers/hub.py

import importlib
import logging

class JarvisHub:
    def __init__(self):
        self._cache = {}
        # Mapeamento fixo de setores para containers
        self.sector_map = {
            "gears": "app.application.containers.gears_container",
            "models": "app.application.containers.models_container",
            "adapters": "app.application.containers.adapters_container",
            "capabilities": "app.application.containers.capabilities_container"
        }

    def resolve(self, cap_id: str, sector: str):
        """O Hub apenas guia o fluxo para o executor correto."""
        key = f"{sector}_{cap_id}"
        if key in self._cache:
            return self._cache[key]

        module_path = self.sector_map.get(sector)
        if not module_path: return None

        try:
            # Carregamento dinâmico do container do setor
            module = importlib.import_module(module_path)
            container_class = getattr(module, f"{sector.capitalize()}Container")
            container = container_class()
            
            # O Hub entrega a função 'execute' mapeada no container
            executor = container.registry.get(cap_id)
            self._cache[key] = executor
            return executor
        except Exception as e:
            logging.error(f"Erro ao guiar para {cap_id} no setor {sector}: {e}")
            return None

hub = JarvisHub()
