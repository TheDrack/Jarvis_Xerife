from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Device Management Service - Handles device registration and capability routing"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.domain.models.device import Capability, Device
from app.application.services.device_location_service import DeviceLocationService
from app.application.services.device_capability_service import DeviceCapabilityService

logger = logging.getLogger(__name__)


class DeviceService(NexusComponent):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

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
        """Backward compatible delegator - see DeviceLocationService.calculate_distance"""
        return DeviceLocationService.calculate_distance(lat1, lon1, lat2, lon2)

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

    def find_device_by_capability(self, capability_name, source_device_id=None, network_id=None, source_lat=None, source_lon=None):
        """Backward compatible delegator - see DeviceCapabilityService.find_device_by_capability"""
        return DeviceCapabilityService(self.engine).find_device_by_capability(
            capability_name, source_device_id, network_id, source_lat, source_lon
        )

    def validate_device_routing(self, source_device_id, target_device_id):
        """Backward compatible delegator - see DeviceCapabilityService.validate_device_routing"""
        return DeviceCapabilityService(self.engine).validate_device_routing(source_device_id, target_device_id)
