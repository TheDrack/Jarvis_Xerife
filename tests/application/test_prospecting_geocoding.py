from app.application.services.prospecting.geocoding import GeocodingService
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeocodingPrecision,
    GeocodingStatus,
)


class FakeGeocoder:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def geocode(self, address: str):
        self.calls += 1
        return self.result.model_copy(update={"address": address})


class FakeRepository:
    def __init__(self):
        self.items = {}

    def get(self, address: str):
        from app.domain.prospecting.geography import address_fingerprint
        return self.items.get(address_fingerprint(address))

    def save(self, result):
        from app.domain.prospecting.geography import address_fingerprint
        self.items[address_fingerprint(result.address)] = result


def result(status=GeocodingStatus.SUCCESS):
    return AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=status,
        coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6) if status is GeocodingStatus.SUCCESS else None,
        precision=GeocodingPrecision.STREET if status is GeocodingStatus.SUCCESS else None,
        provider="fake",
        confidence=0.9 if status is GeocodingStatus.SUCCESS else 0,
    )


def test_service_reuses_successful_geocoding_without_calling_provider_again():
    provider = FakeGeocoder(result())
    repository = FakeRepository()
    service = GeocodingService(provider, repository)

    first = service.geocode("Rua A, 10, São José, SC, Brasil")
    second = service.geocode(" rua a, 10, são josé, sc, brasil ")

    assert provider.calls == 1
    assert first.coordinate == second.coordinate


def test_service_does_not_cache_failed_geocoding_results():
    provider = FakeGeocoder(result(GeocodingStatus.FAILED))
    repository = FakeRepository()
    service = GeocodingService(provider, repository)

    service.geocode("Rua A, 10, São José, SC, Brasil")
    service.geocode("Rua A, 10, São José, SC, Brasil")

    assert provider.calls == 2


def test_service_force_bypasses_cache_and_updates_the_observation():
    first_result = result()
    second_result = first_result.model_copy(update={
        "coordinate": GeoCoordinate(latitude=-27.61, longitude=-48.61)
    })
    provider = FakeGeocoder(first_result)
    repository = FakeRepository()
    service = GeocodingService(provider, repository)

    service.geocode("Rua A, 10, São José, SC, Brasil")
    provider.result = second_result
    refreshed = service.geocode(
        "Rua A, 10, São José, SC, Brasil",
        force=True,
    )

    assert provider.calls == 2
    assert refreshed.coordinate.latitude == -27.61


def test_service_rejects_provider_result_for_a_different_address():
    class MismatchedGeocoder:
        def geocode(self, address: str):
            return result().model_copy(update={"address": "Rua B, 20"})

    service = GeocodingService(MismatchedGeocoder(), FakeRepository())

    import pytest
    with pytest.raises(ValueError, match="different address"):
        service.geocode("Rua A, 10, São José, SC, Brasil")
