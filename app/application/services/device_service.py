# -*- coding: utf-8 -*-
"""Device Management Service - Handles device registration and capability routing"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.domain.models.device import Capability, Device

logger = logging.getLogger(__name__)


class DeviceService:
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

    def register_device(
        self,
        name: str,
        device_type: str,
        capabilities: List[Dict[str, Any]],
    ) -> Optional[int]:
        """
        Register a new device or update an existing one

        Args:
            name: Device name
            device_type: Device type (mobile, desktop, cloud, iot)
            capabilities: List of capability dictionaries

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

    def update_device_status(self, device_id: int, status: str) -> bool:
        """
        Update device status and last_seen timestamp

        Args:
            device_id: ID of the device
            status: New status (online/offline)

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

    def find_device_by_capability(self, capability_name: str) -> Optional[Dict[str, Any]]:
        """
        Find an online device that has a specific capability

        Args:
            capability_name: Name of the required capability

        Returns:
            Device dict with the capability or None if not found
        """
        try:
            with Session(self.engine) as session:
                # Find capabilities with the given name
                cap_statement = select(Capability).where(Capability.name == capability_name)
                capabilities = session.exec(cap_statement).all()

                # Filter to find devices that are online
                for capability in capabilities:
                    device_statement = select(Device).where(
                        Device.id == capability.device_id,
                        Device.status == "online"
                    )
                    device = session.exec(device_statement).first()

                    if device:
                        # Get all capabilities for this device
                        all_caps_statement = select(Capability).where(
                            Capability.device_id == device.id
                        )
                        all_caps = session.exec(all_caps_statement).all()

                        return {
                            "id": device.id,
                            "name": device.name,
                            "type": device.type,
                            "status": device.status,
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

                return None

        except Exception as e:
            logger.error(f"Error finding device by capability: {e}")
            return None
