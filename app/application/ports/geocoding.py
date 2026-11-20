"""Application ports for address geocoding and geocoding persistence."""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.domain.prospecting.geography import AddressGeocoding


@runtime_checkable
class Geocoder(Protocol):
    """Provider adapter; implementations must return precision and provenance."""

    def geocode(self, address: str) -> AddressGeocoding:
        ...


@runtime_checkable
class GeocodingRepository(Protocol):
    """Persistent cache keyed by a normalized address fingerprint."""

    def get(self, address: str) -> Optional[AddressGeocoding]:
        ...

    def save(self, result: AddressGeocoding) -> None:
        ...


__all__ = ["Geocoder", "GeocodingRepository"]
