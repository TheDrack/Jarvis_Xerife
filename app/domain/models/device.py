# -*- coding: utf-8 -*-
"""Device and Capability models for distributed orchestration"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Device(SQLModel, table=True):
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
    last_seen: datetime = Field(default_factory=datetime.now, nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)


class Capability(SQLModel, table=True):
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


class CommandResult(SQLModel, table=True):
    """
    SQLModel table for storing command execution results from devices.
    This enables the feedback loop for distributed command execution.
    """

    __tablename__ = "command_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    command_id: int = Field(foreign_key="interactions.id", nullable=False, index=True)
    executor_device_id: Optional[int] = Field(foreign_key="devices.id", nullable=True, index=True)
    result_data: str = Field(default="{}", nullable=False)  # JSON string for result data
    success: bool = Field(default=False, nullable=False)
    message: str = Field(default="", nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
