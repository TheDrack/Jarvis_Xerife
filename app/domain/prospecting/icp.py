"""Deterministic, explainable Ideal Customer Profile (ICP) fit evaluation.

Fit is derived only from company attributes that were declared against an
explicitly configured profile. Criterion weights are profile data, never a
hardcoded rule: the rubric only becomes meaningful once it is validated against
real commercial results for a specific offer and tenant.

A missing company attribute yields ``UNKNOWN`` rather than ``UNMATCHED`` so that
absent data is never silently reported as incompatibility.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.prospecting.contracts import ProspectCompany


class FitCriterion(str, Enum):
    INDUSTRY = "industry"
    SEGMENT = "segment"
    TERRITORY = "territory"
    SIZE = "size"


class CriterionOutcome(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    UNKNOWN = "unknown"


class IcpWeights(BaseModel):
    """Relative importance of each criterion, supplied per ICP profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    industry: float = Field(default=0.0, ge=0)
    segment: float = Field(default=0.0, ge=0)
    territory: float = Field(default=0.0, ge=0)
    size: float = Field(default=0.0, ge=0)

    def for_criterion(self, criterion: FitCriterion) -> float:
        return {
            FitCriterion.INDUSTRY: self.industry,
            FitCriterion.SEGMENT: self.segment,
            FitCriterion.TERRITORY: self.territory,
            FitCriterion.SIZE: self.size,
        }[criterion]


class CriterionEvaluation(BaseModel):
    """One explainable criterion decision for a single company."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: FitCriterion
    weight: float = Field(ge=0)
    outcome: CriterionOutcome
    detail: str = Field(min_length=1, max_length=500)


class FitAssessment(BaseModel):
    """Fit score with the evidence-bearing breakdown that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    icp_profile_id: str = Field(min_length=1, max_length=120)
    tenant_id: UUID
    fit_score: int = Field(ge=0, le=100)
    fit_threshold: int = Field(ge=0, le=100)
    matched_weight: float = Field(ge=0)
    evaluable_weight: float = Field(ge=0)
    evaluations: tuple[CriterionEvaluation, ...]
    matched_criteria: tuple[FitCriterion, ...] = ()
    unmatched_criteria: tuple[FitCriterion, ...] = ()
    unknown_criteria: tuple[FitCriterion, ...] = ()


class IcpProfile(BaseModel):
    """Tenant-scoped definition of a buyer profile for one commercial offer."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    profile_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    tenant_id: UUID
    offer: Optional[str] = Field(default=None, max_length=200)
    target_industries: tuple[str, ...] = ()
    target_segments: tuple[str, ...] = ()
    target_cities: tuple[str, ...] = ()
    target_states: tuple[str, ...] = ()
    min_employees: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    max_employees: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    weights: IcpWeights
    fit_threshold: int = Field(default=60, ge=0, le=100)
    minimum_confidence: int = Field(default=40, ge=0, le=100)

    @model_validator(mode="after")
    def validate_profile_is_usable(self) -> "IcpProfile":
        configured = {
            FitCriterion.INDUSTRY: bool(self.target_industries),
            FitCriterion.SEGMENT: bool(self.target_segments),
            FitCriterion.TERRITORY: bool(self.target_cities or self.target_states),
            FitCriterion.SIZE: self.min_employees is not None or self.max_employees is not None,
        }
        for criterion, is_configured in configured.items():
            if not is_configured:
                continue
            if self.weights.for_criterion(criterion) <= 0:
                raise ValueError(
                    f"criterion '{criterion.value}' is configured but has no weight"
                )
        if not any(configured.values()):
            raise ValueError("ICP profile must configure at least one target criterion")
        if (
            self.min_employees is not None
            and self.max_employees is not None
            and self.min_employees > self.max_employees
        ):
            raise ValueError("min_employees must not exceed max_employees")
        return self


def normalize_text(value: str) -> str:
    """Accent- and case-insensitive form used for conservative phrase matching."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = re.sub(r"[^a-z0-9]+", " ", without_accents.casefold())
    return " ".join(collapsed.split())


def _matches_any(value: str, targets: tuple[str, ...]) -> bool:
    """True when a target phrase appears in the value as a whole-word phrase.

    Containment is one-directional on purpose: the configured target must appear
    in the company attribute, so ``"Comunicação Visual"`` matches
    ``"Comunicação Visual e Serralheria"`` but a single generic token does not
    match an unrelated longer profile.
    """
    normalized_value = f" {normalize_text(value)} "
    return any(
        f" {normalize_text(target)} " in normalized_value for target in targets if target
    )


def _text_criterion(
    criterion: FitCriterion,
    *,
    value: Optional[str],
    targets: tuple[str, ...],
    weight: float,
) -> CriterionEvaluation:
    if not value:
        return CriterionEvaluation(
            criterion=criterion,
            weight=weight,
            outcome=CriterionOutcome.UNKNOWN,
            detail=f"company has no {criterion.value} attribute to compare",
        )
    if _matches_any(value, targets):
        return CriterionEvaluation(
            criterion=criterion,
            weight=weight,
            outcome=CriterionOutcome.MATCHED,
            detail=f"{criterion.value} '{value}' matches a configured target",
        )
    return CriterionEvaluation(
        criterion=criterion,
        weight=weight,
        outcome=CriterionOutcome.UNMATCHED,
        detail=f"{criterion.value} '{value}' matches no configured target",
    )


def _territory_criterion(company: ProspectCompany, profile: IcpProfile) -> CriterionEvaluation:
    weight = profile.weights.territory
    missing: list[str] = []
    rejected: list[str] = []

    if profile.target_states:
        if company.state is None:
            missing.append("state")
        elif company.state.upper() not in {state.upper() for state in profile.target_states}:
            rejected.append(f"state '{company.state}'")

    if profile.target_cities:
        if company.city is None:
            missing.append("city")
        elif not _matches_any(company.city, profile.target_cities):
            rejected.append(f"city '{company.city}'")

    if rejected:
        return CriterionEvaluation(
            criterion=FitCriterion.TERRITORY,
            weight=weight,
            outcome=CriterionOutcome.UNMATCHED,
            detail="outside configured territory: " + ", ".join(rejected),
        )
    if missing:
        return CriterionEvaluation(
            criterion=FitCriterion.TERRITORY,
            weight=weight,
            outcome=CriterionOutcome.UNKNOWN,
            detail="company has no " + " or ".join(missing) + " attribute to compare",
        )
    return CriterionEvaluation(
        criterion=FitCriterion.TERRITORY,
        weight=weight,
        outcome=CriterionOutcome.MATCHED,
        detail="company is inside the configured territory",
    )


def _size_criterion(company: ProspectCompany, profile: IcpProfile) -> CriterionEvaluation:
    weight = profile.weights.size
    if company.employee_count is None:
        return CriterionEvaluation(
            criterion=FitCriterion.SIZE,
            weight=weight,
            outcome=CriterionOutcome.UNKNOWN,
            detail="company has no employee_count attribute to compare",
        )

    lower = profile.min_employees
    upper = profile.max_employees
    within_lower = lower is None or company.employee_count >= lower
    within_upper = upper is None or company.employee_count <= upper
    bounds = f"{lower if lower is not None else '-'}..{upper if upper is not None else '-'}"
    if within_lower and within_upper:
        return CriterionEvaluation(
            criterion=FitCriterion.SIZE,
            weight=weight,
            outcome=CriterionOutcome.MATCHED,
            detail=f"employee_count {company.employee_count} is inside {bounds}",
        )
    return CriterionEvaluation(
        criterion=FitCriterion.SIZE,
        weight=weight,
        outcome=CriterionOutcome.UNMATCHED,
        detail=f"employee_count {company.employee_count} is outside {bounds}",
    )


def evaluate_fit(company: ProspectCompany, profile: IcpProfile) -> FitAssessment:
    """Score a company against one ICP profile, keeping every decision explainable.

    The score is the share of *evaluable* weight that matched. Criteria with no
    configured target are not evaluated at all, and criteria whose company
    attribute is missing stay ``UNKNOWN``: they neither help nor penalize, but
    they are reported so the caller can require verification.
    """
    evaluations: list[CriterionEvaluation] = []

    if profile.target_industries:
        evaluations.append(
            _text_criterion(
                FitCriterion.INDUSTRY,
                value=company.industry,
                targets=profile.target_industries,
                weight=profile.weights.industry,
            )
        )
    if profile.target_segments:
        evaluations.append(
            _text_criterion(
                FitCriterion.SEGMENT,
                value=company.segment,
                targets=profile.target_segments,
                weight=profile.weights.segment,
            )
        )
    if profile.target_cities or profile.target_states:
        evaluations.append(_territory_criterion(company, profile))
    if profile.min_employees is not None or profile.max_employees is not None:
        evaluations.append(_size_criterion(company, profile))

    evaluable = [
        evaluation
        for evaluation in evaluations
        if evaluation.outcome is not CriterionOutcome.UNKNOWN
    ]
    matched = [
        evaluation for evaluation in evaluable if evaluation.outcome is CriterionOutcome.MATCHED
    ]
    evaluable_weight = sum(evaluation.weight for evaluation in evaluable)
    matched_weight = sum(evaluation.weight for evaluation in matched)
    fit_score = round(100 * matched_weight / evaluable_weight) if evaluable_weight > 0 else 0

    return FitAssessment(
        icp_profile_id=profile.profile_id,
        tenant_id=profile.tenant_id,
        fit_score=fit_score,
        fit_threshold=profile.fit_threshold,
        matched_weight=matched_weight,
        evaluable_weight=evaluable_weight,
        evaluations=tuple(evaluations),
        matched_criteria=tuple(evaluation.criterion for evaluation in matched),
        unmatched_criteria=tuple(
            evaluation.criterion
            for evaluation in evaluable
            if evaluation.outcome is CriterionOutcome.UNMATCHED
        ),
        unknown_criteria=tuple(
            evaluation.criterion
            for evaluation in evaluations
            if evaluation.outcome is CriterionOutcome.UNKNOWN
        ),
    )
