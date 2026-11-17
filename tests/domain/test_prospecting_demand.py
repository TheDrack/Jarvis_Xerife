from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.prospecting.demand import (
    CandidateType,
    DemandCandidate,
    DemandEvidence,
    DemandIntent,
    DemandRequest,
    MarketDirection,
    RequesterType,
    evaluate_demand_match,
)


def evidence():
    return DemandEvidence(
        source_id="provider.jobs",
        source_name="Authorized job provider",
        url="https://jobs.example/opening/42",
        terms_reference="Provider terms reviewed for discovery",
        collected_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
    )


def job_demand(**overrides):
    data = {
        "tenant_id": uuid4(),
        "requester_id": "candidate-1",
        "requester_type": RequesterType.INDIVIDUAL,
        "direction": MarketDirection.C2B,
        "intent": DemandIntent.FIND_JOBS,
        "title": "Python backend developer",
        "description": "Looking for backend development roles in Python.",
        "categories": ("python", "backend"),
        "city": "São José",
        "state": "SC",
    }
    data.update(overrides)
    return DemandRequest(**data)


def test_job_search_is_c2b_and_profile_is_private_by_default():
    demand = job_demand()
    assert demand.direction is MarketDirection.C2B
    assert demand.consent_to_share_profile is False
    assert demand.profile_reference is None


def test_job_profile_cannot_be_shared_without_scoped_explicit_consent():
    with pytest.raises(ValidationError, match="profile_sharing_requires_explicit_scoped_consent"):
        job_demand(profile_reference="vault://cv/123", consent_to_share_profile=True)


def test_scoped_consent_is_only_valid_for_job_search():
    demand = job_demand(
        profile_reference="vault://cv/123",
        consent_to_share_profile=True,
        consent_recorded_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
        consent_scope="Share this CV only with employer for vacancy 42",
    )
    assert demand.consent_to_share_profile is True


def test_individual_supplier_search_is_b2c_not_c2b():
    demand = DemandRequest(
        tenant_id=uuid4(),
        requester_id="person-1",
        requester_type=RequesterType.INDIVIDUAL,
        direction=MarketDirection.B2C,
        intent=DemandIntent.FIND_SUPPLIERS,
        title="Find a metalworker",
        description="Need a local metalworking supplier for a custom gate.",
        categories=("serralheria",),
        city="São José",
        state="SC",
    )
    assert demand.direction is MarketDirection.B2C


def test_invalid_direction_is_rejected():
    with pytest.raises(ValidationError, match="requester_intent_direction_mismatch"):
        job_demand(direction=MarketDirection.B2B)


def test_matcher_explains_category_and_city_match():
    demand = job_demand()
    candidate = DemandCandidate(
        candidate_id="vacancy-42",
        candidate_type=CandidateType.JOB_OPENING,
        title="Python Backend Developer",
        categories=("python", "backend"),
        city="São José",
        state="SC",
        evidence=evidence(),
    )
    result = evaluate_demand_match(demand, candidate)
    assert result.score == 90
    assert "same_city" in result.reasons
    assert any(reason.startswith("category_match:") for reason in result.reasons)


def test_matcher_rejects_wrong_candidate_type():
    result = evaluate_demand_match(
        job_demand(),
        DemandCandidate(
            candidate_id="company-1",
            candidate_type=CandidateType.COMPANY,
            title="Industrial company",
            categories=("python",),
            evidence=evidence(),
        ),
    )
    assert result.score == 0
    assert result.reasons == ("candidate_type_not_eligible",)


def test_b2c_supplier_search_matches_company_candidates():
    demand = DemandRequest(
        tenant_id=uuid4(),
        requester_id="person-1",
        requester_type=RequesterType.INDIVIDUAL,
        direction=MarketDirection.B2C,
        intent=DemandIntent.FIND_SUPPLIERS,
        title="Find food distributor",
        description="Need a food distributor serving small markets.",
        categories=("food distributor",),
        city="São José",
        state="SC",
    )
    candidate = DemandCandidate(
        candidate_id="company-123",
        candidate_type=CandidateType.COMPANY,
        title="Regional food distributor",
        categories=("food distributor",),
        city="São José",
        state="SC",
        evidence=evidence(),
    )
    assert evaluate_demand_match(demand, candidate).score == 90


def test_demand_evidence_rejects_insecure_http_source():
    with pytest.raises(ValidationError, match="demand_evidence_requires_https"):
        DemandEvidence(
            source_id="untrusted",
            source_name="Untrusted source",
            url="http://jobs.example/opening/42",
            terms_reference="Terms not verified",
        )
