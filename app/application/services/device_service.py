from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Device Management Service - Handles device registration and capability routing"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.domain.models.device import Capability, Device

logger = logging.getLogger(__name__)


class DeviceService(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Service for managing devices and their capabilities in the distributed system.
    Handles device registration, status updates, and capability-based routing.
    """

    def __init__(self, engine):
        """
        Initialize the device service

        Args:
            engine: SQLAlchemy engine for database operations
        """
        self.engine = engine

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two geographic coordinates using Haversine formula.
        
        Args:
            lat1: Latitude of first point
            lon1: Longitude of first point
            lat2: Latitude of second point
            lon2: Longitude of second point
            
        Returns:
            Distance in kilometers
        """
        # Earth's radius in kilometers
        R = 6371.0
        
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        return distance

    def register_device(
        self,
        name: str,
        device_type: str,
        capabilities: List[Dict[str, Any]],
        network_id: Optional[str] = None,
        network_type: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        last_ip: Optional[str] = None,
    ) -> Optional[int]:
        """
        Register a new device or update an existing one

        Args:
            name: Device name
            device_type: Device type (mobile, desktop, cloud, iot)
            capabilities: List of capability dictionaries
            network_id: Optional network identifier (SSID or public IP)
            network_type: Optional network type (wifi, 4g, 5g, ethernet)
            lat: Optional latitude coordinate
            lon: Optional longitude coordinate
            last_ip: Optional last known IP address

        Returns:
            Device ID if successful, None otherwise
        """
        try:
            with Session(self.engine) as session:
                # Check if device with this name already exists
                statement = select(Device).where(Device.name == name)
                existing_device = session.exec(statement).first()

                if existing_device:
                    # Update existing device
                    existing_device.type = device_type
                    existing_device.status = "online"
                    existing_device.network_id = network_id
                    existing_device.network_type = network_type
                    existing_device.lat = lat
                    existing_device.lon = lon
                    existing_device.last_ip = last_ip
                    existing_device.last_seen = datetime.now()
                    session.add(existing_device)
                    session.commit()
                    session.refresh(existing_device)
                    device_id = existing_device.id
                    logger.info(f"Updated existing device: {name} (ID: {device_id})")
                else:
                    # Create new device
                    device = Device(
                        name=name,
                        type=device_type,
                        status="online",
                        network_id=network_id,
                        network_type=network_type,
                        lat=lat,
                        lon=lon,
                        last_ip=last_ip,
                        last_seen=datetime.now(),
                    )
                    session.add(device)
                    session.commit()
                    session.refresh(device)
                    device_id = device.id
                    logger.info(f"Registered new device: {name} (ID: {device_id})")

                # Update capabilities - remove old ones and add new ones
                # Delete existing capabilities for this device
                statement = select(Capability).where(Capability.device_id == device_id)
                old_capabilities = session.exec(statement).all()
                for cap in old_capabilities:
                    session.delete(cap)

                # Add new capabilities
                for cap_data in capabilities:
                    capability = Capability(
                        device_id=device_id,
                        name=cap_data.get("name", ""),
                        description=cap_data.get("description", ""),
                        meta_data=json.dumps(cap_data.get("metadata", {})),
                    )
                    session.add(capability)

                session.commit()
                logger.info(f"Updated {len(capabilities)} capabilities for device {device_id}")

                return device_id

        except Exception as e:
            logger.error(f"Error registering device: {e}")
            return None

    def update_device_status(
        self, 
        device_id: int, 
        status: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        last_ip: Optional[str] = None,
    ) -> bool:
        """
        Update device status and last_seen timestamp

        Args:
            device_id: ID of the device
            status: New status (online/offline)
            lat: Optional latitude coordinate
            lon: Optional longitude coordinate
            last_ip: Optional last known IP address

        Returns:
            True if successful, False otherwise
        """
        try:
            with Session(self.engine) as session:
                statement = select(Device).where(Device.id == device_id)
                device = session.exec(statement).first()

                if device:
                    device.status = status
                    device.last_seen = datetime.now()
                    if lat is not None:
                        device.lat = lat
                    if lon is not None:
                        device.lon = lon
                    if last_ip is not None:
                        device.last_ip = last_ip
                    session.add(device)
                    session.commit()
                    logger.info(f"Updated device {device_id} status to {status}")
                    return True
                else:
                    logger.warning(f"Device {device_id} not found")
                    return False

        except Exception as e:
            logger.error(f"Error updating device status: {e}")
            return False

    def get_device(self, device_id: int) -> Optional[Dict[str, Any]]:
        """
        Get device information with its capabilities

        Args:
            device_id: ID of the device

        Returns:
            Device dict with capabilities or None if not found
        """
        try:
            with Session(self.engine) as session:
                statement = select(Device).where(Device.id == device_id)
                device = session.exec(statement).first()

                if not device:
                    return None

                # Get capabilities
                cap_statement = select(Capability).where(Capability.device_id == device_id)
                capabilities = session.exec(cap_statement).all()

                return {
                    "id": device.id,
                    "name": device.name,
                    "type": device.type,
                    "status": device.status,
                    "network_id": device.network_id,
                    "network_type": device.network_type,
                    "lat": device.lat,
                    "lon": device.lon,
                    "last_ip": device.last_ip,
                    "last_seen": device.last_seen.isoformat(),
                    "capabilities": [
                        {
                            "name": cap.name,
                            "description": cap.description,
                            "metadata": json.loads(cap.meta_data),
                        }
                        for cap in capabilities
                    ],
                }

        except Exception as e:
            logger.error(f"Error getting device: {e}")
            return None

    def list_devices(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all devices with their capabilities

        Args:
            status_filter: Optional status filter (online/offline)

        Returns:
            List of device dictionaries
        """
        try:
            with Session(self.engine) as session:
                statement = select(Device)
                if status_filter:
                    statement = statement.where(Device.status == status_filter)

                devices = session.exec(statement).all()

                result = []
                for device in devices:
                    # Get capabilities for each device
                    cap_statement = select(Capability).where(Capability.device_id == device.id)
                    capabilities = session.exec(cap_statement).all()

                    result.append({
                        "id": device.id,
                        "name": device.name,
                        "type": device.type,
                        "status": device.status,
                        "network_id": device.network_id,
                        "network_type": device.network_type,
                        "lat": device.lat,
                        "lon": device.lon,
                        "last_ip": device.last_ip,
                        "last_seen": device.last_seen.isoformat(),
                        "capabilities": [
                            {
                                "name": cap.name,
                                "description": cap.description,
                                "metadata": json.loads(cap.meta_data),
                            }
                            for cap in capabilities
                        ],
                    })

                return result

        except Exception as e:
            logger.error(f"Error listing devices: {e}")
            return []

    def find_device_by_capability(
        self,
        capability_name: str,
        source_device_id: Optional[int] = None,
        network_id: Optional[str] = None,
        source_lat: Optional[float] = None,
        source_lon: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find an online device that has a specific capability using intelligent routing.
        
        Priority hierarchy:
        1. Source device itself (if it has the capability)
        2. Devices on the same network (proximity)
        3. Devices within 1km radius (very close geographically)
        4. Devices within 50km radius (same city)
        5. Other online devices (fallback)

        Args:
            capability_name: Name of the required capability
            source_device_id: ID of the device that originated the command
            network_id: Network identifier (SSID or public IP) for proximity routing
            source_lat: Source device latitude for geolocation routing
            source_lon: Source device longitude for geolocation routing

        Returns:
            Device dict with the capability or None if not found
        """
        try:
            with Session(self.engine) as session:
                # Find all capabilities with the given name
                cap_statement = select(Capability).where(Capability.name == capability_name)
                capabilities = session.exec(cap_statement).all()

                # Build list of candidate devices with priority scoring
                candidates = []
                
                for capability in capabilities:
                    device_statement = select(Device).where(
                        Device.id == capability.device_id,
                        Device.status == "online"
                    )
                    device = session.exec(device_statement).first()

                    if device:
                        # Calculate priority score
                        priority = 0
                        distance = None
                        
                        # Priority 1: Source device (highest priority)
                        if source_device_id and device.id == source_device_id:
                            priority = 100
                            logger.info(f"Source device {device.id} ({device.name}) has capability '{capability_name}'")
                        # Priority 2: Same network (high priority)
                        elif network_id and device.network_id == network_id:
                            priority = 80
                            logger.info(f"Device {device.id} ({device.name}) on same network '{network_id}' has capability '{capability_name}'")
                        # Priority 3: Very close geographically (within 1km)
                        elif (source_lat is not None and source_lon is not None and 
                              device.lat is not None and device.lon is not None):
                            distance = self.calculate_distance(source_lat, source_lon, device.lat, device.lon)
                            if distance < 1.0:  # Within 1km
                                priority = 70
                                logger.info(f"Device {device.id} ({device.name}) is very close ({distance:.2f}km) for capability '{capability_name}'")
                            elif distance < 50.0:  # Within 50km (same city)
                                priority = 40
                                logger.info(f"Device {device.id} ({device.name}) is nearby ({distance:.2f}km) for capability '{capability_name}'")
                            else:
                                priority = 10
                                logger.debug(f"Device {device.id} ({device.name}) is far ({distance:.2f}km) for capability '{capability_name}'")
                        # Priority 4: Other online devices (fallback)
                        else:
                            priority = 10
                            logger.debug(f"Device {device.id} ({device.name}) available as fallback for capability '{capability_name}'")
                        
                        # Get all capabilities for this device
                        all_caps_statement = select(Capability).where(
                            Capability.device_id == device.id
                        )
                        all_caps = session.exec(all_caps_statement).all()

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
                                "last_ip": device.last_ip,
                                "last_seen": device.last_seen.isoformat(),
                                "capabilities": [
                                    {
                                        "name": cap.name,
                                        "description": cap.description,
                                        "metadata": json.loads(cap.meta_data),
                                    }
                                    for cap in all_caps
                                ],
                            }
                        })

                # Sort by priority (highest first) and return the best match
                if candidates:
                    candidates.sort(key=lambda x: x["priority"], reverse=True)
                    selected = candidates[0]
                    logger.info(
                        f"Selected device {selected['device']['id']} ({selected['device']['name']}) "
                        f"with priority {selected['priority']} for capability '{capability_name}'"
                    )
                    return selected["device"]

                return None

        except Exception as e:
            logger.error(f"Error finding device by capability: {e}")
            return None

    def validate_device_routing(
        self,
        source_device_id: Optional[int],
        target_device_id: int,
    ) -> Dict[str, Any]:
        """
        Validate if routing from source to target device requires user confirmation.
        
        This implements the security and conflict resolution logic:
        - If source is on mobile network (4G/5G) and target is on home network, ask for confirmation
        - If devices are on different networks, flag for potential security concern
        
        Args:
            source_device_id: ID of the device that originated the command
            target_device_id: ID of the device that will execute the command
            
        Returns:
            Dict with validation result:
            - requires_confirmation: bool
            - reason: str (explanation)
            - source_device: dict
            - target_device: dict
        """
        try:
            with Session(self.engine) as session:
                # Get source device if provided
                source_device = None
                if source_device_id:
                    source_statement = select(Device).where(Device.id == source_device_id)
                    source_device = session.exec(source_statement).first()
                
                # Get target device
                target_statement = select(Device).where(Device.id == target_device_id)
                target_device = session.exec(target_statement).first()
                
                if not target_device:
                    return {
                        "requires_confirmation": False,
                        "reason": "Target device not found",
                        "source_device": None,
                        "target_device": None,
                    }
                
                # If no source device, no conflict possible
                if not source_device:
                    return {
                        "requires_confirmation": False,
                        "reason": "No source device specified",
                        "source_device": None,
                        "target_device": {
                            "id": target_device.id,
                            "name": target_device.name,
                            "network_type": target_device.network_type,
                        },
                    }
                
                # Check for cross-network routing scenarios
                requires_confirmation = False
                reason = ""
                
                # Calculate distance if both devices have coordinates
                distance = None
                if (source_device.lat is not None and source_device.lon is not None and
                    target_device.lat is not None and target_device.lon is not None):
                    distance = self.calculate_distance(
                        source_device.lat, source_device.lon,
                        target_device.lat, target_device.lon
                    )
                    
                    # Scenario 1: Devices are in different cities (>50km apart)
                    if distance > 50.0:
                        requires_confirmation = True
                        reason = (
                            f"O dispositivo de destino ({target_device.name}) está "
                            f"a {distance:.1f}km de distância. "
                            "Deseja executar a ação remotamente?"
                        )
                        return {
                            "requires_confirmation": requires_confirmation,
                            "reason": reason,
                            "distance": distance,
                            "source_device": {
                                "id": source_device.id,
                                "name": source_device.name,
                                "network_type": source_device.network_type,
                                "network_id": source_device.network_id,
                                "lat": source_device.lat,
                                "lon": source_device.lon,
                            },
                            "target_device": {
                                "id": target_device.id,
                                "name": target_device.name,
                                "network_type": target_device.network_type,
                                "network_id": target_device.network_id,
                                "lat": target_device.lat,
                                "lon": target_device.lon,
                            },
                        }
                
                # Scenario 2: Source on mobile network (4G/5G), target on fixed network (WiFi/Ethernet)
                if (source_device.network_type and target_device.network_type and
                    source_device.network_type in ["4g", "5g"] and 
                    target_device.network_type in ["wifi", "ethernet"]):
                    requires_confirmation = True
                    reason = (
                        f"Você está no {source_device.network_type.upper()} "
                        f"({source_device.name}) mas o dispositivo de destino "
                        f"({target_device.name}) está na rede doméstica. "
                        "Deseja executar mesmo assim?"
                    )
                
                # Scenario 3: Different networks entirely
                elif (source_device.network_id and target_device.network_id and
                      source_device.network_id != target_device.network_id):
                    requires_confirmation = True
                    reason = (
                        f"Você está em uma rede diferente ({source_device.network_id}) "
                        f"do dispositivo de destino ({target_device.network_id}). "
                        "Deseja executar mesmo assim?"
                    )
                
                return {
                    "requires_confirmation": requires_confirmation,
                    "reason": reason,
                    "distance": distance,
                    "source_device": {
                        "id": source_device.id,
                        "name": source_device.name,
                        "network_type": source_device.network_type,
                        "network_id": source_device.network_id,
                        "lat": source_device.lat,
                        "lon": source_device.lon,
                    },
                    "target_device": {
                        "id": target_device.id,
                        "name": target_device.name,
                        "network_type": target_device.network_type,
                        "network_id": target_device.network_id,
                        "lat": target_device.lat,
                        "lon": target_device.lon,
                    },
                }
                
        except Exception as e:
            logger.error(f"Error validating device routing: {e}")
            return {
                "requires_confirmation": False,
                "reason": f"Error during validation: {str(e)}",
                "source_device": None,
                "target_device": None,
            }
