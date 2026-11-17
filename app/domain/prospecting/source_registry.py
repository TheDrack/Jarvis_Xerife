"""Governed catalog of discovery and market-intelligence sources.

A source being catalogued does not imply permission to scrape, persist, or contact
its listed organizations. Acquisition mode, terms review, evidence freshness and
whether the source yields company-level records are explicit.
"""
from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SourceKind(str, Enum):
    COMPANY_REGISTRY = "company_registry"
    ASSOCIATION_DIRECTORY = "association_directory"
    MARKET_INTELLIGENCE = "market_intelligence"
    PUBLIC_STATISTICS = "public_statistics"
    PROCUREMENT = "procurement"
    JOBS = "jobs"
    FUNDING = "funding"
    TRADE = "trade"
    COMPLIANCE = "compliance"
    INNOVATION_ECOSYSTEM = "innovation_ecosystem"
    COMPANY_WEBSITE = "company_website"


class AcquisitionMode(str, Enum):
    OFFICIAL_OPEN_DATA = "official_open_data"
    OFFICIAL_API = "official_api"
    OFFICIAL_EXPORT = "official_export"
    MANUAL_RESEARCH = "manual_research"
    LICENSED_PROVIDER = "licensed_provider"
    AGGREGATE_INDICATORS = "aggregate_indicators"
    NOT_YET_INTEGRATED = "not_yet_integrated"


class SourceStatus(str, Enum):
    AVAILABLE = "available"
    REQUIRES_TERMS_REVIEW = "requires_terms_review"
    REQUIRES_CREDENTIALS = "requires_credentials"
    RESEARCH_ONLY = "research_only"
    PLANNED = "planned"


class ProspectSourceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=180)
    kind: SourceKind
    acquisition_mode: AcquisitionMode
    status: SourceStatus
    homepage: HttpUrl
    description: str = Field(min_length=8, max_length=1000)
    yields_company_records: bool = False
    yields_aggregate_indicators: bool = False
    durable_storage_allowed: Optional[bool] = None
    terms_reviewed_at: Optional[str] = None
    geographic_coverage: tuple[str, ...] = ()
    data_dimensions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class ProspectSourceCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(ge=1)
    sources: tuple[ProspectSourceDefinition, ...]

    @model_validator(mode="after")
    def unique_source_ids(self) -> "ProspectSourceCatalog":
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source_id values must be unique")
        return self

    def get(self, source_id: str) -> ProspectSourceDefinition:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(f"unknown prospecting source: {source_id}")

    def by_kind(self, kind: SourceKind) -> tuple[ProspectSourceDefinition, ...]:
        return tuple(source for source in self.sources if source.kind is kind)

    def available_company_sources(self) -> tuple[ProspectSourceDefinition, ...]:
        return tuple(
            source for source in self.sources
            if source.yields_company_records
            and source.status is SourceStatus.AVAILABLE
            and source.durable_storage_allowed is True
        )


def load_source_catalog(path: Path | str) -> ProspectSourceCatalog:
    """Load and validate the declarative source catalog."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProspectSourceCatalog.model_validate(payload)


__all__ = [
    "AcquisitionMode",
    "ProspectSourceCatalog",
    "ProspectSourceDefinition",
    "SourceKind",
    "SourceStatus",
    "load_source_catalog",
]
