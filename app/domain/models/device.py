from app.core.nexuscomponent import NexusComponent
import logging
logger = logging.getLogger(__name__)
# -*- coding: utf-8 -*-
"""Device and Capability models for distributed orchestration"""

from datetime import datetime
from typing import Optional, List
import json

from sqlmodel import Field, SQLModel, Column, JSON


class Device(NexusComponent, SQLModel, table=True):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    """
    SQLModel table for storing registered devices in the distributed system.
    Devices can be mobile phones, desktops, IoT devices, or cloud instances.
    """

    __tablename__ = "devices"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, index=True)
    type: str = Field(nullable=False)  # mobile, desktop, cloud, iot
    status: str = Field(default="offline", nullable=False)  # online, offline
    network_id: Optional[str] = Field(default=None, nullable=True)  # SSID or public IP for proximity routing
    network_type: Optional[str] = Field(default=None, nullable=True)  # wifi, 4g, 5g, ethernet
    lat: Optional[float] = Field(default=None, nullable=True)  # Latitude for geolocation
    lon: Optional[float] = Field(default=None, nullable=True)  # Longitude for geolocation
    last_ip: Optional[str] = Field(default=None, nullable=True)  # Last known IP address
    last_seen: datetime = Field(default_factory=datetime.now, nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    vendor_brand: str | None = None
    
    # CORREÇÃO AQUI: Mapeando a lista para JSON para compatibilidade com SQLite
    vulnerabilities: List[str] = Field(
        default=[], 
        sa_column=Column(JSON)
    )
    
    conversion_potential: float = 0.0  # 0.0 a 1.0
    is_recruitable: bool = False
    last_threat_scan: datetime | None = None
    inherited_location: bool = False # Define se a localização vem de um vizinho


class Capability(NexusComponent, SQLModel, table=True):
    """
    SQLModel table for storing device capabilities.
    Each device can have multiple capabilities like camera access, bluetooth scanning, etc.
    """

    __tablename__ = "capabilities"

    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id", nullable=False, index=True)
    name: str = Field(nullable=False, index=True)  # e.g., 'camera', 'bluetooth_scan', 'local_http_request'
    description: str = Field(default="", nullable=False)
    meta_data: str = Field(default="{}", nullable=False)  # JSON string for technical details
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)


class CommandResult(NexusComponent, SQLModel, table=True):
    """
    SQLModel table for storing command execution results from devices.
    This enables the feedback loop for distributed command execution.
    """

    __tablename__ = "command_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    command_id: int = Field(nullable=False, index=True)
    executor_device_id: Optional[int] = Field(foreign_key="devices.id", nullable=True, index=True)
    result_data: str = Field(default="{}", nullable=False)  # JSON string for result data
    success: bool = Field(default=False, nullable=False)
    message: str = Field(default="", nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
