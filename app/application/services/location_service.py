from app.core.nexuscomponent import NexusComponent
from app.domain.models.device import Device
import logging
logger = logging.getLogger(__name__)

class LocationService(NexusComponent):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def __init__(self, device_repository):
        self.repo = device_repository

    async def update_mesh_location(self, target_device: Device):
        """Se o dispositivo não tem GPS, herda do soldado mais próximo."""
        if target_device.lat and target_device.lon:
            return target_device

        # Busca soldados ativos em um raio próximo via IP ou rede local
        nearby_soldier = await self.repo.find_nearest_active_soldier(target_device)
        
        if nearby_soldier:
            target_device.lat = nearby_soldier.lat
            target_device.lon = nearby_soldier.lon
            target_device.inherited_location = True
            await self.repo.update(target_device)
        
        return target_device
