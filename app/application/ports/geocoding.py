"""Application ports for address geocoding and geocoding persistence."""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from app.domain.prospecting.contracts import ProspectCompany
from app.domain.prospecting.geography import AddressGeocoding


@runtime_checkable
class Geocoder(Protocol):
    """Single-address provider adapter."""

    def geocode(self, address: str) -> AddressGeocoding:
        ...


@runtime_checkable
class CompanyGeocoder(Protocol):
    """Structured, batch-capable provider for company postal addresses."""

    def geocode_companies(
        self, companies: Sequence[ProspectCompany]
    ) -> list[AddressGeocoding]:
        ...


@runtime_checkable
class GeocodingRepository(Protocol):
    """Persistent cache keyed by a normalized address fingerprint."""

    def get(self, address: str) -> Optional[AddressGeocoding]:
        ...

    def save(self, result: AddressGeocoding) -> None:
        ...


__all__ = ["CompanyGeocoder", "Geocoder", "GeocodingRepository"]
