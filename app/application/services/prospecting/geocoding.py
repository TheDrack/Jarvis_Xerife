"""Application service coordinating geocoding providers and persistent cache."""
from __future__ import annotations

from typing import Sequence

from app.application.ports.geocoding import (
    CompanyGeocoder,
    Geocoder,
    GeocodingRepository,
)
from app.domain.prospecting.contracts import ProspectCompany
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeocodingStatus,
    address_fingerprint,
)


class GeocodingService:
    """Geocode addresses and reuse successful or approximate observations.

    Failed lookups are deliberately not cached: temporary provider/network
    failures must not permanently poison an address. A caller can force a fresh
    lookup by passing force=True.
    """

    def __init__(
        self,
        geocoder: Geocoder | CompanyGeocoder,
        repository: GeocodingRepository,
    ) -> None:
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
        self._validate_and_cache(address, result)
        return result

    def geocode_company(
        self, company: ProspectCompany, *, force: bool = False
    ) -> AddressGeocoding:
        return self.geocode_companies([company], force=force)[0]

    def geocode_companies(
        self,
        companies: Sequence[ProspectCompany],
        *,
        force: bool = False,
    ) -> list[AddressGeocoding]:
        """Geocode structured company addresses in one provider batch when supported."""
        if not companies:
            return []

        addresses = []
        unique_companies = {}
        results_by_fingerprint = {}
        for company in companies:
            address = company.geocoding_address
            if not address:
                raise ValueError(
                    f"company {company.company_name!r} has no postal address to geocode"
                )
            fingerprint = address_fingerprint(address)
            addresses.append((fingerprint, address))
            if fingerprint in unique_companies:
                continue
            unique_companies[fingerprint] = company
            if not force:
                cached = self._repository.get(address)
                if cached is not None and cached.status in {
                    GeocodingStatus.SUCCESS,
                    GeocodingStatus.PARTIAL,
                }:
                    results_by_fingerprint[fingerprint] = cached

        pending = [
            (fingerprint, company)
            for fingerprint, company in unique_companies.items()
            if fingerprint not in results_by_fingerprint
        ]
        if pending:
            batch_method = getattr(self._geocoder, "geocode_companies", None)
            if callable(batch_method):
                provider_results = batch_method([company for _, company in pending])
            else:
                provider_results = [
                    self._geocoder.geocode(company.geocoding_address)
                    for _, company in pending
                ]
            if len(provider_results) != len(pending):
                raise ValueError("geocoder returned an unexpected number of batch results")

            for (fingerprint, company), result in zip(
                pending, provider_results, strict=True
            ):
                self._validate_and_cache(company.geocoding_address, result)
                results_by_fingerprint[fingerprint] = result

        return [results_by_fingerprint[fingerprint] for fingerprint, _ in addresses]

    def _validate_and_cache(
        self, address: str, result: AddressGeocoding
    ) -> None:
        if address_fingerprint(result.address) != address_fingerprint(address):
            raise ValueError("geocoder returned a result for a different address")
        if result.status in {GeocodingStatus.SUCCESS, GeocodingStatus.PARTIAL}:
            self._repository.save(result)


__all__ = ["GeocodingService"]
