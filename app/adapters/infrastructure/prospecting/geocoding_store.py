"""DuckDB persistence for address-geocoding observations.

This repository intentionally uses a dedicated database file. The CNPJ analytical
store is optimized for bulk reads and remains read-only during campaigns; keeping
geocoding writes separate avoids writer contention with its ingestion/query path.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.domain.prospecting.geography import (
    AddressGeocoding,
    GeoCoordinate,
    GeocodingPrecision,
    GeocodingStatus,
    address_fingerprint,
)


class DuckDBGeocodingRepository:
    """Persistent geocoding cache keyed by normalized address SHA-256."""

    def __init__(self, database: Path | str) -> None:
        self._database = Path(database)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prospect_geocoding (
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
                "ALTER TABLE prospect_geocoding ADD COLUMN IF NOT EXISTS formatted_address VARCHAR"
            )
        finally:
            connection.close()

    def _connect(self):
        import duckdb

        self._database.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self._database))

    def get(self, address: str) -> Optional[AddressGeocoding]:
        key = address_fingerprint(address)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT address, formatted_address, status, latitude, longitude, accuracy_m,
                       geocoding_precision, provider, confidence, geocoded_at
                FROM prospect_geocoding
                WHERE address_hash = ?
                """,
                [key],
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None
        (
            stored_address,
            formatted_address,
            status,
            latitude,
            longitude,
            accuracy_m,
            precision,
            provider,
            confidence,
            geocoded_at,
        ) = row
        coordinate = None
        if latitude is not None and longitude is not None:
            coordinate = GeoCoordinate(
                latitude=latitude,
                longitude=longitude,
                accuracy_m=accuracy_m,
            )
        return AddressGeocoding(
            address=stored_address,
            formatted_address=formatted_address,
            status=GeocodingStatus(status),
            coordinate=coordinate,
            precision=GeocodingPrecision(precision) if precision else None,
            provider=provider,
            confidence=confidence,
            geocoded_at=datetime.fromisoformat(geocoded_at),
        )

    def save(self, result: AddressGeocoding) -> None:
        key = address_fingerprint(result.address)
        coordinate = result.coordinate
        connection = self._connect()
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                "DELETE FROM prospect_geocoding WHERE address_hash = ?",
                [key],
            )
            connection.execute(
                """
                INSERT INTO prospect_geocoding (
                    address_hash, address, formatted_address, status, latitude, longitude,
                    accuracy_m, geocoding_precision, provider, confidence, geocoded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    key,
                    result.address,
                    result.formatted_address,
                    result.status.value,
                    coordinate.latitude if coordinate else None,
                    coordinate.longitude if coordinate else None,
                    coordinate.accuracy_m if coordinate else None,
                    result.precision.value if result.precision else None,
                    result.provider,
                    result.confidence,
                    result.geocoded_at.isoformat(),
                ],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = ["DuckDBGeocodingRepository"]
