from app.application.services.prospecting.geocoding import GeocodingService
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
)
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeocodingPrecision,
    GeocodingStatus,
    address_fingerprint,
)


def make_company(name, street_number):
    evidence = ProspectEvidence(
        source_id="fixture",
        source_name="Fixture",
        source_type=ProspectEvidenceType.USER_PROVIDED,
        url="https://example.com",
        license_or_terms="fixture",
        supports_fields=("postal_address",),
    )
    return ProspectCompany(
        company_name=name,
        street_type="RUA",
        street_name="DAS FLORES",
        street_number=street_number,
        neighborhood="CENTRO",
        postal_code="88010000",
        city="SAO JOSE",
        state="SC",
        evidence=(evidence,),
    )


class MemoryGeocodingRepository:
    def __init__(self):
        self.items = {}

    def get(self, address):
        return self.items.get(address_fingerprint(address))

    def save(self, result):
        self.items[address_fingerprint(result.address)] = result


class FakeCompanyBatchGeocoder:
    def __init__(self):
        self.calls = []

    def geocode_companies(self, companies):
        self.calls.append(list(companies))
        return [
            AddressGeocoding(
                address=company.geocoding_address,
                status=GeocodingStatus.PARTIAL,
                coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6),
                precision=GeocodingPrecision.STREET,
                provider="fake-batch",
            )
            for company in companies
        ]


def test_service_sends_unique_uncached_companies_in_one_batch_and_restores_order():
    first = make_company("Empresa A", "10")
    second = make_company("Empresa B", "20")
    duplicate = make_company("Empresa A - unidade repetida", "10")
    provider = FakeCompanyBatchGeocoder()
    service = GeocodingService(provider, MemoryGeocodingRepository())

    results = service.geocode_companies([first, second, duplicate])

    assert len(provider.calls) == 1
    assert provider.calls[0] == [first, second]
    assert len(results) == 3
    assert results[0] == results[2]
    assert results[0].address == first.geocoding_address
    assert results[1].address == second.geocoding_address


def test_service_reuses_cached_batch_results_without_calling_provider_again():
    company = make_company("Empresa A", "10")
    provider = FakeCompanyBatchGeocoder()
    service = GeocodingService(provider, MemoryGeocodingRepository())

    first = service.geocode_company(company)
    second = service.geocode_company(company)

    assert len(provider.calls) == 1
    assert first == second


def test_service_retries_failed_batch_results_instead_of_caching_them():
    company = make_company("Empresa A", "10")

    class FailedBatchGeocoder:
        def __init__(self):
            self.calls = 0

        def geocode_companies(self, companies):
            self.calls += 1
            return [
                AddressGeocoding(
                    address=item.geocoding_address,
                    status=GeocodingStatus.FAILED,
                    provider="fake-failure",
                )
                for item in companies
            ]

    provider = FailedBatchGeocoder()
    service = GeocodingService(provider, MemoryGeocodingRepository())

    service.geocode_company(company)
    service.geocode_company(company)

    assert provider.calls == 2


def test_service_rejects_company_without_geocodable_address():
    evidence = ProspectEvidence(
        source_id="fixture",
        source_name="Fixture",
        source_type=ProspectEvidenceType.USER_PROVIDED,
        url="https://example.com",
        license_or_terms="fixture",
        supports_fields=("company_name",),
    )
    company = ProspectCompany(company_name="Sem endereço", evidence=(evidence,))
    service = GeocodingService(FakeCompanyBatchGeocoder(), MemoryGeocodingRepository())

    import pytest
    with pytest.raises(ValueError, match="no postal address"):
        service.geocode_company(company)
