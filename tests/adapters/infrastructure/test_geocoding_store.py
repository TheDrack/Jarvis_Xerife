from app.adapters.infrastructure.prospecting.geocoding_store import DuckDBGeocodingRepository
from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeocodingPrecision,
    GeocodingStatus,
)


def test_duckdb_geocoding_repository_round_trips_geocoding_and_precision(tmp_path):
    repository = DuckDBGeocodingRepository(tmp_path / "geo.duckdb")
    result = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        formatted_address="Rua A, 10 - Centro, São José - SC, Brasil",
        status=GeocodingStatus.SUCCESS,
        coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6, accuracy_m=20),
        precision=GeocodingPrecision.ROOFTOP,
        provider="test-geocoder",
        confidence=0.97,
    )

    repository.save(result)
    loaded = repository.get(" rua a, 10, são josé, sc, brasil ")

    assert loaded is not None
    assert loaded.formatted_address == "Rua A, 10 - Centro, São José - SC, Brasil"
    assert loaded.coordinate.latitude == -27.6
    assert loaded.coordinate.longitude == -48.6
    assert loaded.precision is GeocodingPrecision.ROOFTOP
    assert loaded.provider == "test-geocoder"


def test_duckdb_geocoding_repository_preserves_unknown_confidence(tmp_path):
    repository = DuckDBGeocodingRepository(tmp_path / "geo.duckdb")
    result = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=GeocodingStatus.SUCCESS,
        coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6),
        precision=GeocodingPrecision.STREET,
        provider="provider-without-confidence",
        confidence=None,
    )

    repository.save(result)

    loaded = repository.get(result.address)
    assert loaded is not None
    assert loaded.confidence is None


def test_duckdb_geocoding_repository_upserts_changed_result_for_same_address(tmp_path):
    repository = DuckDBGeocodingRepository(tmp_path / "geo.duckdb")
    original = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=GeocodingStatus.SUCCESS,
        coordinate=GeoCoordinate(latitude=-27.6, longitude=-48.6),
        precision=GeocodingPrecision.STREET,
        provider="provider-a",
        confidence=0.8,
    )
    corrected = original.model_copy(update={
        "coordinate": GeoCoordinate(latitude=-27.61, longitude=-48.61),
        "provider": "provider-b",
        "confidence": 0.99,
    })

    repository.save(original)
    repository.save(corrected)

    loaded = repository.get(original.address)
    assert loaded.coordinate.latitude == -27.61
    assert loaded.provider == "provider-b"


def test_duckdb_geocoding_repository_round_trips_coordinate_crs(tmp_path):
    repository = DuckDBGeocodingRepository(tmp_path / "geo-crs.duckdb")
    result = AddressGeocoding(
        address="Rua A, 10, São José, SC, Brasil",
        status=GeocodingStatus.PARTIAL,
        coordinate=GeoCoordinate(
            latitude=-27.6,
            longitude=-48.6,
            accuracy_m=800,
            crs="EPSG:4674",
        ),
        precision=GeocodingPrecision.POSTAL_CODE,
        provider="geocodebr:cnefe",
    )

    repository.save(result)
    loaded = repository.get(result.address)

    assert loaded is not None
    assert loaded.coordinate.crs == "EPSG:4674"
