"""Ports for provider-neutral geospatial OSINT discovery."""
from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.domain.intelligence.osint import (
    Coordinate,
    GeoLocation,
    Host,
    NetworkRange,
    Signal,
)


class GeoProvider(Protocol):
    def locate(self, ip: str) -> GeoLocation: ...


class NetworkResolver(Protocol):
    def resolve(self, ip: str) -> NetworkRange: ...


class PassiveIntel(Protocol):
    def query_radius(
        self, coord: Coordinate, radius_km: float, filters: dict[str, Any]
    ) -> Sequence[Host | Signal]: ...


class SignalSource(Protocol):
    def capture(self, duration_s: float) -> Sequence[Signal]: ...


class ActiveScanner(Protocol):
    def scan(self, targets: Sequence[str], ports: Sequence[int]) -> Sequence[Host]: ...


class CachePort(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
