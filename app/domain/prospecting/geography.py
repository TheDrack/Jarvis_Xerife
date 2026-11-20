"""Geospatial domain contracts for address geocoding and proximity queries.

Coordinates always carry precision and provenance. A locality or postal-code
centroid must never be represented as a rooftop result.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeocodingStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class GeocodingPrecision(str, Enum):
    ROOFTOP = "rooftop"
    PREMISE = "premise"
    STREET = "street"
    INTERPOLATED = "interpolated"
    POSTAL_CODE = "postal_code"
    LOCALITY = "locality"
    REGION = "region"
    UNKNOWN = "unknown"


class GeoCoordinate(BaseModel):
    """Geographic coordinate with explicit CRS and estimated accuracy radius."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    crs: str = Field(default="EPSG:4326", min_length=5, max_length=32)


class AddressGeocoding(BaseModel):
    """One geocoding observation for an address, with explicit uncertainty."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    address: str = Field(min_length=1, max_length=1000)
    formatted_address: Optional[str] = Field(default=None, max_length=1000)
    status: GeocodingStatus
    coordinate: Optional[GeoCoordinate] = None
    precision: Optional[GeocodingPrecision] = None
    provider: str = Field(min_length=1, max_length=120)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    geocoded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "AddressGeocoding":
        if self.geocoded_at.tzinfo is None or self.geocoded_at.utcoffset() is None:
            raise ValueError("geocoded_at must include a timezone")
        if self.status in {GeocodingStatus.SUCCESS, GeocodingStatus.PARTIAL}:
            if self.coordinate is None or self.precision is None:
                raise ValueError("geocoded results require coordinates and precision")
        elif self.coordinate is not None or self.precision is not None:
            raise ValueError("pending/failed geocoding cannot claim coordinates or precision")
        return self


class GeoRadiusQuery(BaseModel):
    """A WGS84 center and a bounded radius, expressed in kilometers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    center: GeoCoordinate
    radius_km: float = Field(gt=0, le=10_000)


def normalize_address(address: str) -> str:
    """Canonicalize whitespace and case without discarding address components."""
    normalized = unicodedata.normalize("NFKC", address)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def address_fingerprint(address: str) -> str:
    """Stable SHA-256 key for cache identity; not a substitute for address validation."""
    normalized = normalize_address(address)
    if not normalized:
        raise ValueError("address must not be blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def distance_km(origin: GeoCoordinate, destination: GeoCoordinate) -> float:
    """Great-circle distance between two WGS84 coordinates (Haversine)."""
    earth_radius_km = 6371.0088
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(destination.longitude - origin.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(min(1.0, haversine)))


__all__ = [
    "AddressGeocoding",
    "GeoCoordinate",
    "GeoRadiusQuery",
    "GeocodingPrecision",
    "GeocodingStatus",
    "address_fingerprint",
    "distance_km",
    "normalize_address",
]
