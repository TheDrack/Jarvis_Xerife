# -*- coding: utf-8 -*-
"""Soldier domain models for the Soldier Mesh (Authorized C2) protocol.

Uses Pydantic for strict validation of all telemetry payloads received from
Soldier devices (PC, Android via Termux, Raspberry Pi, etc.).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SoldierStatus(str, Enum):
    """Operational status of a Soldier device."""

    ONLINE = "online"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"


class SoldierRegistration(BaseModel):
    """Data required to register a new Soldier with the C2 hub."""

    soldier_id: str = Field(..., description="Unique identifier for the Soldier device.")
    public_key: str = Field(..., description="RSA/Ed25519 public key (PEM format) for tunnel auth.")
    device_type: str = Field(
        default="unknown", description="Device category: pc, android, raspberry_pi, iot, etc."
    )
    alias: Optional[str] = Field(default=None, description="Human-readable name for the Soldier.")

    @field_validator("soldier_id")
    @classmethod
    def soldier_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("soldier_id must not be empty")
        return v.strip()

    @field_validator("public_key")
    @classmethod
    def public_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("public_key must not be empty")
        return v.strip()


class SoldierRecord(BaseModel):
    """Full Soldier record stored in the registry."""

    soldier_id: str
    public_key: str
    device_type: str = "unknown"
    alias: Optional[str] = None
    status: SoldierStatus = SoldierStatus.OFFLINE
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: Optional[datetime] = None

    # Last known location
    lat: Optional[float] = None
    lon: Optional[float] = None
    last_ip: Optional[str] = None

    # Last system snapshot
    battery_pct: Optional[float] = None
    cpu_pct: Optional[float] = None
    ram_pct: Optional[float] = None


class LocationPayload(BaseModel):
    """GPS or IP-based location reported by a Soldier."""

    soldier_id: str
    lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    lon: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    ip: Optional[str] = None
    accuracy_m: Optional[float] = Field(default=None, ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NearbyDevice(BaseModel):
    """A Bluetooth or Wi-Fi device detected in the Soldier's environment."""

    mac_address: str
    signal_dbm: Optional[int] = None
    protocol: str = Field(default="wifi", description="'wifi' or 'bluetooth'")
    ssid: Optional[str] = Field(default=None, description="SSID (Wi-Fi only).")
    vendor: Optional[str] = None


class SystemState(BaseModel):
    """CPU / RAM / battery snapshot reported by a Soldier."""

    soldier_id: str
    battery_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    cpu_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    ram_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryPayload(BaseModel):
    """Full periodic telemetry bundle sent by a Soldier device."""

    soldier_id: str
    location: Optional[LocationPayload] = None
    nearby_devices: List[NearbyDevice] = Field(default_factory=list)
    system_state: Optional[SystemState] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
