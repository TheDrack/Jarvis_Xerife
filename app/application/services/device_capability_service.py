# -*- coding: utf-8 -*-
"""Device Capability Service - Capability-based device routing and validation.
CORREÇÃO: Eliminação real de N+1 com Eager Loading e proteções de comparação.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select, col
from sqlalchemy.orm import selectinload
from app.domain.models.device import Capability, Device

# Mock do serviço de localização para manter integridade do código
try:
    from app.application.services.device_location_service import DeviceLocationService
except ImportError:
    class DeviceLocationService:
        @staticmethod
        def calculate_distance(lat1, lon1, lat2, lon2): return 0.0

logger = logging.getLogger(__name__)

class DeviceCapabilityService:
    """Service for capability-based device routing with optimized queries."""
    
    def __init__(self, engine):
        self.engine = engine
    
    def find_device_by_capability(
        self,
        capability_name: str,
        source_device_id: Optional[int] = None,
        network_id: Optional[str] = None,
        source_lat: Optional[float] = None,
        source_lon: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Busca um dispositivo online com capacidade específica usando Eager Loading."""
        try:
            with Session(self.engine) as session:
                # CORREÇÃO: selectinload carrega todas as capabilities relacionadas 
                # de uma vez, eliminando o N+1 dentro do loop.
                statement = (
                    select(Device)
                    .join(Capability)
                    .where(
                        Capability.name == capability_name,
                        Device.status == "online"
                    )
                    .options(selectinload(Device.capabilities))
                )
                
                devices = session.exec(statement).all()
                
                if not devices:
                    return None
                
                candidates = []
                for device in devices:
                    priority = 10
                    distance = None
                    
                    # Cálculo de Prioridade
                    if source_device_id and device.id == source_device_id:
                        priority = 100
                    elif network_id and device.network_id == network_id:
                        priority = 80
                    elif (source_lat is not None and source_lon is not None and
                          device.lat is not None and device.lon is not None):
                        distance = DeviceLocationService.calculate_distance(
                            source_lat, source_lon, device.lat, device.lon
                        )
                        if distance < 1.0: priority = 70
                        elif distance < 50.0: priority = 40

                    # Processamento de Capabilities (sem novas queries ao banco)
                    processed_caps = []
                    for cap in device.capabilities:
                        try:
                            meta = json.loads(cap.meta_data) if cap.meta_data else {}
                        except json.JSONDecodeError:
                            meta = {}
                        processed_caps.append({
                            "name": cap.name,
                            "description": cap.description,
                            "metadata": meta
                        })
                    
                    candidates.append({
                        "priority": priority,
                        "distance": distance,
                        "device": {
                            "id": device.id,
                            "name": device.name,
                            "type": device.type,
                            "status": device.status,
                            "network_id": device.network_id,
                            "network_type": device.network_type,
                            "lat": device.lat,
                            "lon": device.lon,
                            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                            "capabilities": processed_caps
                        }
                    })
                
                if candidates:
                    candidates.sort(key=lambda x: x["priority"], reverse=True)
                    return candidates[0]["device"]
                
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar dispositivo por capacidade: {e}")
            return None

    def validate_device_routing(
        self,
        source_device_id: Optional[int],
        target_device_id: int,
    ) -> Dict[str, Any]:
        """Valida se o roteamento exige confirmação humana (cross-network ou longa distância)."""
        try:
            with Session(self.engine) as session:
                source_device = None
                if source_device_id:
                    source_device = session.get(Device, source_device_id)
                
                target_device = session.get(Device, target_device_id)
                
                if not target_device:
                    return {"requires_confirmation": False, "reason": "Destino não encontrado"}
                
                if not source_device:
                    return {"requires_confirmation": False, "target_device": {"id": target_device.id}}
                
                distance = None
                if (source_device.lat is not None and source_device.lon is not None and
                    target_device.lat is not None and target_device.lon is not None):
                    distance = DeviceLocationService.calculate_distance(
                        source_device.lat, source_device.lon,
                        target_device.lat, target_device.lon
                    )
                
                # CORREÇÃO: Comparação segura contra None
                if distance is not None and distance > 50.0:
                    return {
                        "requires_confirmation": True,
                        "reason": f"Dispositivo a {distance:.1f}km. Executar remotamente?",
                        "distance": distance,
                        "source_device": {"id": source_device.id, "name": source_device.name},
                        "target_device": {"id": target_device.id, "name": target_device.name}
                    }
                
                # Lógica de Redes
                requires_conf = False
                reason = ""
                
                if (source_device.network_type in ["4g", "5g"] and 
                    target_device.network_type in ["wifi", "ethernet"]):
                    requires_conf = True
                    reason = "Você está em rede móvel e o destino está em rede fixa."
                elif (source_device.network_id and target_device.network_id and 
                      source_device.network_id != target_device.network_id):
                    requires_conf = True
                    reason = f"Redes diferentes: {source_device.network_id} -> {target_device.network_id}"
                
                return {
                    "requires_confirmation": requires_conf,
                    "reason": reason,
                    "distance": distance,
                    "source_device": {"id": source_device.id, "name": source_device.name},
                    "target_device": {"id": target_device.id, "name": target_device.name}
                }
        except Exception as e:
            logger.error(f"Erro na validação de roteamento: {e}")
            return {"requires_confirmation": False, "error": str(e)}
