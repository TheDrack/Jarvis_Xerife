"""Typed, provenance-preserving contracts for B2B company prospects.

Personal contact data is deliberately outside this first domain slice. Company
records require a tenant boundary and at least one traceable source reference.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProspectEvidenceType(str, Enum):
    COMPANY_WEBSITE = "company_website"
    PUBLIC_REGISTRY = "public_registry"
    PUBLIC_DIRECTORY = "public_directory"
    USER_PROVIDED = "user_provided"
    AUTHORIZED_PROVIDER = "authorized_provider"


class RegistryPresence(str, Enum):
    """Whether the company was found in the public company registry.

    A prospect can be a real buyer without being in the Receita extract (informal
    business, establishment registered elsewhere, divergent activity code). The
    deliverable must say which case it is instead of implying registry coverage.
    """

    FOUND = "found"
    NOT_FOUND = "not_found"
    UNVERIFIED = "unverified"


class ProspectStage(str, Enum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    MEETING_SCHEDULED = "meeting_scheduled"
    PROPOSAL_SENT = "proposal_sent"
    CUSTOMER = "customer"
    DISQUALIFIED = "disqualified"
    DO_NOT_CONTACT = "do_not_contact"


class ProspectEvidence(BaseModel):
    """Traceable source for a company attribute; remote content is untrusted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=160)
    source_type: ProspectEvidenceType
    url: HttpUrl
    license_or_terms: str = Field(min_length=1, max_length=500)
    supports_fields: tuple[str, ...] = Field(min_length=1, max_length=20)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None


    @field_validator("supports_fields")
    @classmethod
    def validate_supported_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value or len(value) > 80 for value in normalized):
            raise ValueError("supported field names must contain 1-80 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("supported field names must be unique")
        return normalized


class ProspectCompany(BaseModel):
    """Business-level identity only; no personal contact details."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=240)
    cnpj: Optional[str] = Field(default=None, min_length=14, max_length=18)
    website: Optional[HttpUrl] = None
    industry: Optional[str] = Field(default=None, max_length=120)
    segment: Optional[str] = Field(default=None, max_length=120)
    employee_count: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    country: str = Field(default="BR", min_length=2, max_length=2)
    registry_presence: Optional[RegistryPresence] = None
    evidence: tuple[ProspectEvidence, ...] = Field(min_length=1, max_length=20)

    @field_validator("cnpj")
    @classmethod
    def normalize_cnpj(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        if len(digits) != 14:
            raise ValueError("CNPJ must contain exactly 14 digits")
        return digits

    @field_validator("state", "country")
    @classmethod
    def normalize_region_code(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value is not None else None


class ProspectStageChange(BaseModel):
    """Append-only domain event for a prospect pipeline transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    previous_stage: ProspectStage
    new_stage: ProspectStage
    actor_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProspectRecord(BaseModel):
    """Tenant-scoped prospect aggregate with an auditable stage history."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prospect_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    company: ProspectCompany
    stage: ProspectStage = ProspectStage.DISCOVERED
    stage_history: tuple[ProspectStageChange, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
