"""Application service coordinating geocoding providers and persistent cache."""
from __future__ import annotations

from app.application.ports.geocoding import Geocoder, GeocodingRepository
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeocodingStatus,
    address_fingerprint,
)


class GeocodingService:
    """Geocode an address once and reuse successful or approximate observations.

    Failed lookups are deliberately not cached: temporary provider/network
    failures must not permanently poison an address. A caller can force a fresh
    lookup by passing force=True.
    """

    def __init__(self, geocoder: Geocoder, repository: GeocodingRepository) -> None:
        self._geocoder = geocoder
        self._repository = repository

    def geocode(
        self, address: str, *, force: bool = False
    ) -> AddressGeocoding:
        if not address or not address.strip():
            raise ValueError("address must not be blank")

        cached = None if force else self._repository.get(address)
        if cached is not None and cached.status in {
            GeocodingStatus.SUCCESS,
            GeocodingStatus.PARTIAL,
        }:
            return cached

        result = self._geocoder.geocode(address.strip())
        if address_fingerprint(result.address) != address_fingerprint(address):
            raise ValueError("geocoder returned a result for a different address")
        if result.status in {GeocodingStatus.SUCCESS, GeocodingStatus.PARTIAL}:
            self._repository.save(result)
        return result


__all__ = ["GeocodingService"]
