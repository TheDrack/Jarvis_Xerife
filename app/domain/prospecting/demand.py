"""Demand-oriented discovery across B2B, B2C and C2B markets.

A demand is a private search request. It is not a public profile and does not
authorize contact, CV sharing, or disclosure of personal data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequesterType(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class MarketDirection(StrEnum):
    B2B = "b2b"
    B2C = "b2c"
    C2B = "c2b"


class DemandIntent(StrEnum):
    FIND_SUPPLIERS = "find_suppliers"
    FIND_CUSTOMERS = "find_customers"
    FIND_JOBS = "find_jobs"
    FIND_SERVICE_PROVIDERS = "find_service_providers"
    FIND_PRODUCTS = "find_products"
    FIND_PARTNERS = "find_partners"
    OFFER_SKILLS = "offer_skills"


class DemandStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class CandidateType(StrEnum):
    COMPANY = "company"
    JOB_OPENING = "job_opening"
    SERVICE = "service"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"


class DemandEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=8, max_length=2048)
    terms_reference: str = Field(min_length=1, max_length=500)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DemandRequest(BaseModel):
    """Private, tenant-scoped statement of what a person or business needs."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    demand_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    requester_id: str = Field(min_length=1, max_length=200)
    requester_type: RequesterType
    direction: MarketDirection
    intent: DemandIntent
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    categories: tuple[str, ...] = Field(min_length=1, max_length=30)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    country: str = Field(default="BR", min_length=2, max_length=2)
    remote_allowed: bool = False
    radius_km: Optional[int] = Field(default=None, ge=1, le=500)
    status: DemandStatus = DemandStatus.DRAFT

    # CV/profile sharing is opt-in and scoped to a specific request.
    profile_reference: Optional[str] = Field(default=None, max_length=512)
    consent_to_share_profile: bool = False
    consent_recorded_at: Optional[datetime] = None
    consent_scope: Optional[str] = Field(default=None, max_length=500)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("state", "country")
    @classmethod
    def normalize_region(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(value.strip().casefold() for value in values))
        if any(not value or len(value) > 100 for value in normalized):
            raise ValueError("demand categories must contain 1-100 characters")
        return normalized

    @model_validator(mode="after")
    def validate_market_and_consent(self):
        allowed = {
            (RequesterType.BUSINESS, DemandIntent.FIND_SUPPLIERS): MarketDirection.B2B,
            (RequesterType.BUSINESS, DemandIntent.FIND_CUSTOMERS): MarketDirection.B2B,
            (RequesterType.BUSINESS, DemandIntent.FIND_PARTNERS): MarketDirection.B2B,
            (RequesterType.BUSINESS, DemandIntent.FIND_SERVICE_PROVIDERS): MarketDirection.B2B,
            (RequesterType.BUSINESS, DemandIntent.FIND_PRODUCTS): MarketDirection.B2B,
            (RequesterType.INDIVIDUAL, DemandIntent.FIND_JOBS): MarketDirection.C2B,
            (RequesterType.INDIVIDUAL, DemandIntent.OFFER_SKILLS): MarketDirection.C2B,
            (RequesterType.INDIVIDUAL, DemandIntent.FIND_SUPPLIERS): MarketDirection.B2C,
            (RequesterType.INDIVIDUAL, DemandIntent.FIND_SERVICE_PROVIDERS): MarketDirection.B2C,
            (RequesterType.INDIVIDUAL, DemandIntent.FIND_PRODUCTS): MarketDirection.B2C,
        }
        expected = allowed.get((self.requester_type, self.intent))
        if expected is None or self.direction != expected:
            raise ValueError("requester_intent_direction_mismatch")
        if self.consent_to_share_profile:
            if self.intent != DemandIntent.FIND_JOBS:
                raise ValueError("profile_sharing_only_applies_to_job_search")
            if not self.profile_reference or not self.consent_recorded_at or not self.consent_scope:
                raise ValueError("profile_sharing_requires_explicit_scoped_consent")
        elif self.consent_recorded_at is not None or self.consent_scope is not None:
            raise ValueError("consent_metadata_without_consent")
        if self.profile_reference and self.intent != DemandIntent.FIND_JOBS:
            raise ValueError("profile_reference_only_applies_to_job_search")
        return self


class DemandCandidate(BaseModel):
    """A source-backed opportunity returned by a discovery adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(min_length=1, max_length=200)
    candidate_type: CandidateType
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    categories: tuple[str, ...] = Field(default=(), max_length=30)
    city: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default=None, min_length=2, max_length=2)
    country: str = Field(default="BR", min_length=2, max_length=2)
    remote: bool = False
    company_id: Optional[str] = Field(default=None, max_length=64)
    evidence: DemandEvidence


class DemandMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    demand_id: UUID
    candidate_id: str
    score: int = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=10)
    matched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def evaluate_demand_match(demand: DemandRequest, candidate: DemandCandidate) -> DemandMatch:
    """Explainable deterministic ranking; no contact or profile disclosure occurs."""
    expected_types = {
        DemandIntent.FIND_SUPPLIERS: {CandidateType.COMPANY},
        DemandIntent.FIND_CUSTOMERS: {CandidateType.COMPANY},
        DemandIntent.FIND_JOBS: {CandidateType.JOB_OPENING},
        DemandIntent.FIND_SERVICE_PROVIDERS: {CandidateType.COMPANY, CandidateType.SERVICE},
        DemandIntent.FIND_PRODUCTS: {CandidateType.COMPANY, CandidateType.PRODUCT},
        DemandIntent.FIND_PARTNERS: {CandidateType.COMPANY, CandidateType.PARTNERSHIP},
        DemandIntent.OFFER_SKILLS: {CandidateType.JOB_OPENING, CandidateType.PARTNERSHIP},
    }
    if candidate.candidate_type not in expected_types[demand.intent]:
        return DemandMatch(
            demand_id=demand.demand_id, candidate_id=candidate.candidate_id,
            score=0, reasons=("candidate_type_not_eligible",),
        )

    score = 0
    reasons: list[str] = []
    wanted = set(demand.categories)
    offered = {value.strip().casefold() for value in candidate.categories}
    overlap = wanted & offered
    if overlap:
        score += 60
        reasons.append("category_match:" + ",".join(sorted(overlap)[:5]))

    same_country = demand.country == candidate.country
    same_state = same_country and demand.state and candidate.state and demand.state == candidate.state
    same_city = same_state and demand.city and candidate.city and demand.city.casefold() == candidate.city.casefold()
    if same_city:
        score += 30
        reasons.append("same_city")
    elif same_state:
        score += 20
        reasons.append("same_state")
    elif same_country:
        score += 5
        reasons.append("same_country")
    elif demand.remote_allowed and candidate.remote:
        score += 15
        reasons.append("remote_compatible")

    if demand.remote_allowed and candidate.remote and "remote_compatible" not in reasons:
        score += 10
        reasons.append("remote_available")
    if not reasons:
        reasons.append("no_strong_match_signal")

    return DemandMatch(
        demand_id=demand.demand_id,
        candidate_id=candidate.candidate_id,
        score=min(score, 100),
        reasons=tuple(reasons),
    )


__all__ = [
    "CandidateType", "DemandCandidate", "DemandEvidence", "DemandIntent",
    "DemandMatch", "DemandRequest", "DemandStatus", "MarketDirection",
    "RequesterType", "evaluate_demand_match",
]
