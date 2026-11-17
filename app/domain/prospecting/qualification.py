"""Deterministic qualification: ICP fit, explicit intent and evidence confidence.

The three dimensions are kept separate on purpose. A compatible segment, a large
company or a polished website never prove buying intent: intent exists only when
an explicit, dated and traceable signal was recorded. Confidence describes how
well the company profile itself is evidenced, not how promising it is.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectRecord,
)
from app.domain.prospecting.icp import FitAssessment, IcpProfile, evaluate_fit


class IntentSignalType(str, Enum):
    """Observable company behaviour that can support a buying hypothesis."""

    HIRING = "hiring"
    EXPANSION = "expansion"
    PUBLIC_TENDER = "public_tender"
    NEW_FACILITY = "new_facility"
    CAPACITY_INVESTMENT = "capacity_investment"
    INBOUND_REQUEST = "inbound_request"
    REFERRAL = "referral"
    OTHER = "other"


class IntentStrength(str, Enum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class QualificationTier(str, Enum):
    PRIORITY = "priority"
    OUTBOUND = "outbound"
    NOT_FIT = "not_fit"


class IntentSignal(BaseModel):
    """One dated, source-backed observation; remote content stays untrusted."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    signal_type: IntentSignalType
    description: str = Field(min_length=1, max_length=500)
    evidence: ProspectEvidence
    observed_at: datetime
    expires_at: Optional[datetime] = None

    @field_validator("observed_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("intent signal timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_expiry(self) -> "IntentSignal":
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("expires_at must be later than observed_at")
        return self


class IntentPolicy(BaseModel):
    """Recency window and strength bands; tune per tenant, never per model call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_days: int = Field(default=90, ge=1, le=730)
    moderate_min_types: int = Field(default=2, ge=1, le=8)
    strong_min_types: int = Field(default=3, ge=2, le=8)

    @model_validator(mode="after")
    def validate_bands(self) -> "IntentPolicy":
        if self.strong_min_types <= self.moderate_min_types:
            raise ValueError("strong_min_types must exceed moderate_min_types")
        return self


class IntentAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strength: IntentStrength
    active_signals: tuple[IntentSignal, ...] = ()
    distinct_signal_types: int = Field(default=0, ge=0)
    stale_or_expired_signals: int = Field(default=0, ge=0)
    window_days: int = Field(ge=1)


class ConfidenceAssessment(BaseModel):
    """Rubric-based evidence confidence: transparency over false precision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int = Field(ge=0, le=100)
    distinct_source_count: int = Field(ge=0)
    distinct_source_type_count: int = Field(ge=0)
    freshest_evidence_at: Optional[datetime] = None
    rationale: tuple[str, ...] = ()


class QualificationAssessment(BaseModel):
    """Result of qualifying one prospect against one ICP profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prospect_id: UUID
    icp_profile_id: str = Field(min_length=1, max_length=120)
    fit: FitAssessment
    intent: IntentAssessment
    confidence: ConfidenceAssessment
    tier: QualificationTier
    needs_verification: bool
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Evidence confidence rubric. These constants are a documented, deterministic
# rubric, not a calibrated probability.
_COVERAGE_POINTS = {1: 40, 2: 55}
_COVERAGE_POINTS_CAPPED = 65
_RECENT_EVIDENCE_BONUS = 20
_SOURCE_TYPE_DIVERSITY_BONUS = 15
_DEFAULT_RECENCY_DAYS = 180


def assess_confidence(
    company: ProspectCompany,
    *,
    now: Optional[datetime] = None,
    recency_days: int = _DEFAULT_RECENCY_DAYS,
) -> ConfidenceAssessment:
    """Score how well the company profile itself is evidenced.

    More independent sources, fresher collection and different source types
    raise confidence. This never says anything about the company's interest.
    """
    reference = now or datetime.now(timezone.utc)
    evidence = company.evidence

    sources = {(item.source_id, str(item.url)) for item in evidence}
    source_types = {item.source_type for item in evidence}
    timestamps = [
        item.verified_at or item.collected_at for item in evidence if item.collected_at
    ]
    freshest = max(timestamps) if timestamps else None

    source_count = len(sources)
    score = min(_COVERAGE_POINTS.get(source_count, _COVERAGE_POINTS_CAPPED), _COVERAGE_POINTS_CAPPED)
    rationale = [f"{source_count} distinct evidence source(s)"]

    if freshest is not None and reference - freshest <= timedelta(days=recency_days):
        score += _RECENT_EVIDENCE_BONUS
        rationale.append(f"evidence collected within {recency_days} days")
    elif freshest is not None:
        rationale.append(f"evidence older than {recency_days} days")

    if len(source_types) >= 2:
        score += _SOURCE_TYPE_DIVERSITY_BONUS
        rationale.append(f"{len(source_types)} independent source types")

    return ConfidenceAssessment(
        score=min(score, 100),
        distinct_source_count=source_count,
        distinct_source_type_count=len(source_types),
        freshest_evidence_at=freshest,
        rationale=tuple(rationale),
    )


def assess_intent(
    signals: tuple[IntentSignal, ...] = (),
    *,
    now: Optional[datetime] = None,
    policy: Optional[IntentPolicy] = None,
) -> IntentAssessment:
    """Keep only signals that are recent and still valid, then band the strength.

    Strength counts *distinct* signal types: five job postings are still a
    hiring signal, not five independent reasons to buy.
    """
    reference = now or datetime.now(timezone.utc)
    active_policy = policy or IntentPolicy()
    window = timedelta(days=active_policy.window_days)

    active: list[IntentSignal] = []
    stale = 0
    for signal in signals:
        is_fresh = timedelta(0) <= (reference - signal.observed_at) <= window
        is_valid = signal.expires_at is None or signal.expires_at > reference
        if is_fresh and is_valid:
            active.append(signal)
        else:
            stale += 1

    distinct_types = len({signal.signal_type for signal in active})
    if distinct_types >= active_policy.strong_min_types:
        strength = IntentStrength.STRONG
    elif distinct_types >= active_policy.moderate_min_types:
        strength = IntentStrength.MODERATE
    elif distinct_types >= 1:
        strength = IntentStrength.WEAK
    else:
        strength = IntentStrength.NONE

    return IntentAssessment(
        strength=strength,
        active_signals=tuple(active),
        distinct_signal_types=distinct_types,
        stale_or_expired_signals=stale,
        window_days=active_policy.window_days,
    )


def qualify_prospect(
    prospect: ProspectRecord,
    profile: IcpProfile,
    *,
    intent_signals: tuple[IntentSignal, ...] = (),
    intent_policy: Optional[IntentPolicy] = None,
    now: Optional[datetime] = None,
) -> QualificationAssessment:
    """Qualify a prospect inside its own tenant.

    ``PRIORITY`` requires both a fit above the profile threshold and an explicit
    intent signal. A well-fitting company with no signal stays ``OUTBOUND``: it
    belongs on a cold outreach list, never in the same bucket as a warm lead.
    """
    if prospect.tenant_id != profile.tenant_id:
        raise ValueError("prospect and ICP profile belong to different tenants")

    reference = now or datetime.now(timezone.utc)
    fit = evaluate_fit(prospect.company, profile)
    intent = assess_intent(intent_signals, now=reference, policy=intent_policy)
    confidence = assess_confidence(prospect.company, now=reference)

    if fit.fit_score < profile.fit_threshold:
        tier = QualificationTier.NOT_FIT
    elif intent.strength in {IntentStrength.MODERATE, IntentStrength.STRONG}:
        tier = QualificationTier.PRIORITY
    else:
        tier = QualificationTier.OUTBOUND

    return QualificationAssessment(
        prospect_id=prospect.prospect_id,
        icp_profile_id=profile.profile_id,
        fit=fit,
        intent=intent,
        confidence=confidence,
        tier=tier,
        needs_verification=bool(fit.unknown_criteria)
        or confidence.score < profile.minimum_confidence,
        assessed_at=reference,
    )


__all__ = [
    "ConfidenceAssessment",
    "IntentAssessment",
    "IntentPolicy",
    "IntentSignal",
    "IntentSignalType",
    "IntentStrength",
    "QualificationAssessment",
    "QualificationTier",
    "assess_confidence",
    "assess_intent",
    "qualify_prospect",
]
