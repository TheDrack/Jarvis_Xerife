import pytest
from pydantic import ValidationError

from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeoRadiusQuery,
    GeocodingPrecision,
    GeocodingStatus,
    address_fingerprint,
    distance_km,
)
from app.domain.prospecting.contracts import ProspectCompany, ProspectEvidence


def test_coordinate_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        GeoCoordinate(latitude=91, longitude=0)
    with pytest.raises(ValidationError):
        GeoCoordinate(latitude=0, longitude=181)


def test_successful_geocoding_requires_coordinates_and_precision():
    with pytest.raises(ValidationError):
        AddressGeocoding(
            address="Rua A, 10, São José, SC, Brasil",
            status=GeocodingStatus.SUCCESS,
            provider="test",
            confidence=0.99,
        )


def test_geocoding_records_precision_and_provenance():
    result = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=GeocodingStatus.SUCCESS,
        coordinate=GeoCoordinate(latitude=-27.6136, longitude=-48.6366, accuracy_m=15),
        precision=GeocodingPrecision.ROOFTOP,
        provider="test-geocoder",
        confidence=0.98,
    )

    assert result.coordinate.latitude == pytest.approx(-27.6136)
    assert result.precision is GeocodingPrecision.ROOFTOP
    assert result.confidence == pytest.approx(0.98)


def test_geocoding_can_keep_provider_confidence_unknown():
    result = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=GeocodingStatus.SUCCESS,
        coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6),
        precision=GeocodingPrecision.STREET,
        provider="provider-without-confidence-score",
    )

    assert result.confidence is None


def test_partial_geocoding_requires_an_explicit_precision():
    with pytest.raises(ValidationError):
        AddressGeocoding(
            address="Centro, São José, SC, Brasil",
            status=GeocodingStatus.PARTIAL,
            coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6),
            provider="test-geocoder",
            confidence=0.5,
        )


def test_failed_geocoding_cannot_claim_coordinates():
    with pytest.raises(ValidationError):
        AddressGeocoding(
            address="Rua inexistente",
            status=GeocodingStatus.FAILED,
            coordinate=GeoCoordinate(latitude=-27, longitude=-48),
            provider="test-geocoder",
            confidence=0,
        )


def test_address_fingerprint_is_stable_for_case_and_whitespace():
    first = address_fingerprint("  Rua A, 10  - São José/SC ")
    second = address_fingerprint("rua a, 10 - são josé/sc")

    assert first == second
    assert len(first) == 64


def test_radius_query_and_haversine_distance():
    origin = GeoCoordinate(latitude=-27.5954, longitude=-48.5480)
    nearby = GeoCoordinate(latitude=-27.6000, longitude=-48.5500)
    radius = GeoRadiusQuery(center=origin, radius_km=1)

    assert distance_km(origin, nearby) < radius.radius_km
    with pytest.raises(ValidationError):
        GeoRadiusQuery(center=origin, radius_km=0)


def test_company_without_address_does_not_produce_a_geocoding_query():
    evidence = ProspectEvidence(
        source_id="registry",
        source_name="Public registry",
        source_type="public_registry",
        url="https://registry.example/company",
        license_or_terms="Public registry terms.",
        supports_fields=("company_name",),
    )
    company = ProspectCompany(company_name="No Address Ltda", evidence=(evidence,))

    assert company.geocoding_address is None



def test_distance_rejects_coordinates_with_different_crs():
    import pytest

    from app.domain.prospecting.geography import distance_km

    origin = GeoCoordinate(latitude=-27.6, longitude=-48.6, crs="EPSG:4326")
    destination = GeoCoordinate(latitude=-27.61, longitude=-48.61, crs="EPSG:4674")

    with pytest.raises(ValueError, match="same coordinate reference system"):
        distance_km(origin, destination)
