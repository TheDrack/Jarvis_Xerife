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
        network_id: Optional[str] = None,
        network_type: Optional[str] = None,
    ) -> Optional[int]:
        """
        Register a new device or update an existing one

        Args:
            name: Device name
            device_type: Device type (mobile, desktop, cloud, iot)
            capabilities: List of capability dictionaries
            network_id: Optional network identifier (SSID or public IP)
            network_type: Optional network type (wifi, 4g, 5g, ethernet)

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
                    "network_id": device.network_id,
                    "network_type": device.network_type,
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
    ) -> Optional[Dict[str, Any]]:
        """
        Find an online device that has a specific capability using intelligent routing.
        
        Priority hierarchy:
        1. Source device itself (if it has the capability)
        2. Devices on the same network (proximity)
        3. Other online devices (fallback)

        Args:
            capability_name: Name of the required capability
            source_device_id: ID of the device that originated the command
            network_id: Network identifier (SSID or public IP) for proximity routing

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
                        
                        # Priority 1: Source device (highest priority)
                        if source_device_id and device.id == source_device_id:
                            priority = 100
                            logger.info(f"Source device {device.id} ({device.name}) has capability '{capability_name}'")
                        # Priority 2: Same network (medium priority)
                        elif network_id and device.network_id == network_id:
                            priority = 50
                            logger.info(f"Device {device.id} ({device.name}) on same network '{network_id}' has capability '{capability_name}'")
                        # Priority 3: Other online devices (fallback)
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
                            "device": {
                                "id": device.id,
                                "name": device.name,
                                "type": device.type,
                                "status": device.status,
                                "network_id": device.network_id,
                                "network_type": device.network_type,
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
                
                # Scenario 1: Source on mobile network (4G/5G), target on fixed network (WiFi/Ethernet)
                if (source_device.network_type in ["4g", "5g"] and 
                    target_device.network_type in ["wifi", "ethernet"]):
                    requires_confirmation = True
                    reason = (
                        f"Você está no {source_device.network_type.upper()} "
                        f"({source_device.name}) mas o dispositivo de destino "
                        f"({target_device.name}) está na rede doméstica. "
                        "Deseja executar mesmo assim?"
                    )
                
                # Scenario 2: Different networks entirely
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
                    "source_device": {
                        "id": source_device.id,
                        "name": source_device.name,
                        "network_type": source_device.network_type,
                        "network_id": source_device.network_id,
                    },
                    "target_device": {
                        "id": target_device.id,
                        "name": target_device.name,
                        "network_type": target_device.network_type,
                        "network_id": target_device.network_id,
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
