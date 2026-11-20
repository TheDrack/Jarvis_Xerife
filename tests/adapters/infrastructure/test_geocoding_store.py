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


def test_geocoding_store_migrates_existing_rows_to_default_crs(tmp_path):
    import duckdb

    from app.domain.prospecting.geography import address_fingerprint

    database = tmp_path / "legacy-geo.duckdb"
    address = "Rua A, 10, São José, SC, Brasil"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        CREATE TABLE prospect_geocoding (
            address_hash VARCHAR PRIMARY KEY,
            address VARCHAR NOT NULL,
            formatted_address VARCHAR,
            status VARCHAR NOT NULL,
            latitude DOUBLE,
            longitude DOUBLE,
            accuracy_m DOUBLE,
            geocoding_precision VARCHAR,
            provider VARCHAR NOT NULL,
            confidence DOUBLE,
            geocoded_at VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO prospect_geocoding VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            address_fingerprint(address),
            address,
            None,
            "success",
            -27.6,
            -48.6,
            25,
            "premise",
            "legacy-provider",
            0.9,
            "2026-11-20T00:00:00+00:00",
        ],
    )
    connection.close()

    repository = DuckDBGeocodingRepository(database)
    loaded = repository.get(address)

    assert loaded is not None
    assert loaded.coordinate.crs == "EPSG:4326"
