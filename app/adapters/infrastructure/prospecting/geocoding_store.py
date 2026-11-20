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
                    coordinate_crs VARCHAR NOT NULL DEFAULT 'EPSG:4326',
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
            connection.execute(
                "ALTER TABLE prospect_geocoding ADD COLUMN IF NOT EXISTS coordinate_crs VARCHAR DEFAULT 'EPSG:4326'"
            )
            connection.execute(
                """
                UPDATE prospect_geocoding
                SET coordinate_crs = 'EPSG:4674'
                WHERE provider = 'geocodebr:cnefe'
                  AND coordinate_crs = 'EPSG:4326'
                """
            )
        finally:
            connection.close()

    def _connect(self):
        import duckdb

        self._database.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self._database))

    def get(self, address: str) -> Optional[AddressGeocoding]:
        key = address_fingerprint(address)
        return self.get_many([address]).get(key)

    def get_many(
        self, addresses: list[str] | tuple[str, ...]
    ) -> dict[str, AddressGeocoding]:
        """Read many cached addresses through one DuckDB connection.

        Results are keyed by the normalized address fingerprint so callers can
        restore input order and deduplicate aliases without another query.
        """
        keys = tuple(dict.fromkeys(address_fingerprint(item) for item in addresses))
        if not keys:
            return {}

        connection = self._connect()
        try:
            rows = []
            for offset in range(0, len(keys), 1000):
                chunk = keys[offset : offset + 1000]
                placeholders = ", ".join("?" for _ in chunk)
                rows.extend(
                    connection.execute(
                        f"""
                        SELECT address_hash, address, formatted_address, status, latitude,
                               longitude, accuracy_m, coordinate_crs, geocoding_precision,
                               provider, confidence, geocoded_at
                        FROM prospect_geocoding
                        WHERE address_hash IN ({placeholders})
                        """,
                        list(chunk),
                    ).fetchall()
                )
        finally:
            connection.close()

        results = {}
        for row in rows:
            (
                key,
                stored_address,
                formatted_address,
                status,
                latitude,
                longitude,
                accuracy_m,
                coordinate_crs,
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
                    crs=coordinate_crs or "EPSG:4326",
                )
            results[key] = AddressGeocoding(
                address=stored_address,
                formatted_address=formatted_address,
                status=GeocodingStatus(status),
                coordinate=coordinate,
                precision=GeocodingPrecision(precision) if precision else None,
                provider=provider,
                confidence=confidence,
                geocoded_at=datetime.fromisoformat(geocoded_at),
            )
        return results

    def save(self, result: AddressGeocoding) -> None:
        self.save_many([result])

    def save_many(self, results: list[AddressGeocoding] | tuple[AddressGeocoding, ...]) -> None:
        """Persist a batch of observations in one transaction and connection."""
        if not results:
            return

        rows_by_key = {}
        for result in results:
            coordinate = result.coordinate
            key = address_fingerprint(result.address)
            rows_by_key[key] = (
                key,
                result.address,
                result.formatted_address,
                result.status.value,
                coordinate.latitude if coordinate else None,
                coordinate.longitude if coordinate else None,
                coordinate.accuracy_m if coordinate else None,
                coordinate.crs if coordinate else "EPSG:4326",
                result.precision.value if result.precision else None,
                result.provider,
                result.confidence,
                result.geocoded_at.isoformat(),
            )
        rows = list(rows_by_key.values())

        connection = self._connect()
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.executemany(
                "DELETE FROM prospect_geocoding WHERE address_hash = ?",
                [(row[0],) for row in rows],
            )
            connection.executemany(
                """
                INSERT INTO prospect_geocoding (
                    address_hash, address, formatted_address, status, latitude, longitude,
                    accuracy_m, coordinate_crs, geocoding_precision, provider, confidence, geocoded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()



__all__ = ["DuckDBGeocodingRepository"]
