"""Provider-neutral geospatial OSINT domain contracts.

Hosts and radio signals are separate entities. Adapters return these source
records; only the fusion service is allowed to create Findings with an interest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Coordinate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(ge=0, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=100)

    @field_validator("lat", "lon", "accuracy_m")
    @classmethod
    def finite_values(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("coordinate values must be finite")
        return value


class NetworkRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cidr: str = Field(min_length=3, max_length=64)
    asn: int | None = Field(default=None, ge=1)
    org: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, value: str) -> str:
        return str(ip_network(value, strict=False))


class GeoLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    coordinate: Coordinate | None = None
    geo_confidence: float = Field(ge=0, le=1)
    connection_type: str | None = Field(default=None, max_length=40)
    is_proxy: bool = False


class Host(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ip: str
    ports: tuple[int, ...] = ()
    geo: Coordinate | None = None
    geo_confidence: float = Field(ge=0, le=1)
    sources: tuple[str, ...] = Field(min_length=1)
    connection_type: str | None = Field(default=None, max_length=40)
    is_proxy: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return str(ip_address(value))

    @field_validator("ports")
    @classmethod
    def validate_ports(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(isinstance(port, bool) or not 1 <= port <= 65535 for port in values):
            raise ValueError("ports must be integers between 1 and 65535")
        return tuple(sorted(set(values)))


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: str = Field(min_length=1, max_length=40)
    identifier: str = Field(min_length=1, max_length=160)
    geo: Coordinate | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=100)


Interest = Literal["confirmed", "discrepancy", "novel"]


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entity: Host | Signal
    category: str = Field(min_length=1, max_length=80)
    data: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(min_length=1, max_length=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    geo_confidence: float | None = Field(default=None, ge=0, le=1)
    interest: Interest | None = None

    @model_validator(mode="after")
    def propagate_host_confidence(self) -> "Finding":
        if isinstance(self.entity, Host) and self.geo_confidence is None:
            object.__setattr__(self, "geo_confidence", self.entity.geo_confidence)
        return self
