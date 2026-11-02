"""Provider-neutral, provenance-preserving intelligence event contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class GeoPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class IntelligenceEvidence(BaseModel):
    """Traceable source reference; external content remains untrusted data."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=160)
    url: HttpUrl
    publisher: Optional[str] = Field(default=None, max_length=200)
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    license_or_terms: str = Field(min_length=1, max_length=500)


class IntelligenceEvent(BaseModel):
    """Normalized event shared by feeds, agents, history and future map views."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    summary: Optional[str] = Field(default=None, max_length=4000)
    url: HttpUrl
    published_at: Optional[datetime] = None
    occurred_at: Optional[datetime] = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location: Optional[GeoPoint] = None
    magnitude: Optional[float] = None
    magnitude_unit: Optional[str] = Field(default=None, max_length=40)
    evidence: IntelligenceEvidence


class SourceHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_id: str
    available: bool
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_code: Optional[str] = None


class IntelligenceBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    events: tuple[IntelligenceEvent, ...] = ()
    sources: tuple[SourceHealth, ...] = ()
