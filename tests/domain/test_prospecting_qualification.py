from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectRecord,
)
from app.domain.prospecting.icp import IcpProfile, IcpWeights, evaluate_fit
from app.domain.prospecting.qualification import (
    IntentPolicy,
    IntentSignal,
    IntentSignalType,
    IntentStrength,
    QualificationTier,
    assess_confidence,
    qualify_prospect,
)

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
TENANT = uuid4()


def evidence(
    *,
    source_id: str = "company_website",
    source_type: str = "company_website",
    url: str = "https://example.com/about",
    collected_at: datetime = NOW - timedelta(days=5),
    supports: tuple[str, ...] = ("company_name", "industry", "employee_count"),
) -> ProspectEvidence:
    return ProspectEvidence(
        source_id=source_id,
        source_name=f"Source {source_id}",
        source_type=source_type,
        url=url,
        license_or_terms="Public company information; collected for B2B prospect research.",
        supports_fields=supports,
        collected_at=collected_at,
    )


def company(**overrides) -> ProspectCompany:
    values = dict(
        company_name="Example Industrial Ltda",
        industry="Comunicação Visual e Serralheria",
        segment="Serralheria",
        city="São José",
        state="SC",
        country="BR",
        website="https://example.com",
        employee_count=25,
        evidence=(evidence(),),
    )
    values.update(overrides)
    return ProspectCompany(**values)


def prospect_for(entity: ProspectCompany, *, tenant_id=TENANT) -> ProspectRecord:
    return ProspectRecord(tenant_id=tenant_id, company=entity)


def profile(**overrides) -> IcpProfile:
    values = dict(
        profile_id="icp-metalworking-sc",
        name="Metalworking buyers in Greater Florianópolis",
        tenant_id=TENANT,
        target_industries=("Comunicação Visual",),
        target_cities=("São José",),
        target_states=("SC",),
        weights=IcpWeights(industry=0.5, territory=0.5),
    )
    values.update(overrides)
    return IcpProfile(**values)


def signal(
    signal_type: IntentSignalType,
    *,
    observed_at: datetime = NOW - timedelta(days=3),
    expires_at: datetime = None,
) -> IntentSignal:
    return IntentSignal(
        signal_type=signal_type,
        description="Observable public signal recorded for B2B research.",
        evidence=evidence(source_id="public_notice", source_type="public_directory"),
        observed_at=observed_at,
        expires_at=expires_at,
    )


def test_fit_scores_only_the_configured_criteria():
    assessment = evaluate_fit(company(), profile())

    assert assessment.fit_score == 100
    assert set(assessment.matched_criteria) == {"industry", "territory"}
    assert assessment.unknown_criteria == ()
    assert assessment.evaluable_weight == pytest.approx(1.0)


def test_criterion_weights_drive_the_resulting_score():
    assessment = evaluate_fit(
        company(industry="Software House", city="São José", state="SC"),
        profile(weights=IcpWeights(industry=0.8, territory=0.2)),
    )

    assert assessment.fit_score == 20
    assert assessment.unmatched_criteria == ("industry",)


def test_missing_company_attribute_is_unknown_and_requires_verification():
    assessment = qualify_prospect(
        prospect_for(company(employee_count=None)),
        profile(
            min_employees=10,
            max_employees=99,
            weights=IcpWeights(industry=0.4, territory=0.4, size=0.2),
        ),
        now=NOW,
    )

    assert assessment.fit.unknown_criteria == ("size",)
    assert assessment.fit.fit_score == 100
    assert assessment.needs_verification is True


def test_company_outside_the_configured_territory_is_not_fit():
    assessment = qualify_prospect(
        prospect_for(company(city="Porto Alegre", state="RS")),
        profile(),
        now=NOW,
    )

    assert assessment.fit.fit_score == 50
    assert assessment.tier is QualificationTier.NOT_FIT


def test_configured_criterion_without_weight_is_rejected():
    with pytest.raises(ValidationError):
        profile(weights=IcpWeights(industry=1.0))


def test_profile_without_any_configured_criterion_is_rejected():
    with pytest.raises(ValidationError):
        IcpProfile(
            profile_id="icp-empty",
            name="No criteria",
            tenant_id=TENANT,
            weights=IcpWeights(industry=1.0),
        )


def test_profile_rejects_inverted_employee_range():
    with pytest.raises(ValidationError):
        profile(
            min_employees=100,
            max_employees=10,
            weights=IcpWeights(industry=1.0, size=1.0),
        )


def test_qualification_rejects_a_profile_from_another_tenant():
    with pytest.raises(ValueError):
        qualify_prospect(prospect_for(company()), profile(tenant_id=uuid4()), now=NOW)


def test_perfect_fit_alone_never_produces_intent():
    assessment = qualify_prospect(prospect_for(company()), profile(), now=NOW)

    assert assessment.fit.fit_score == 100
    assert assessment.intent.strength is IntentStrength.NONE
    assert assessment.intent.active_signals == ()
    assert assessment.tier is QualificationTier.OUTBOUND


def test_explicit_distinct_signals_promote_the_prospect_to_priority():
    assessment = qualify_prospect(
        prospect_for(company()),
        profile(),
        intent_signals=(
            signal(IntentSignalType.HIRING),
            signal(IntentSignalType.EXPANSION),
        ),
        now=NOW,
    )

    assert assessment.intent.strength is IntentStrength.MODERATE
    assert assessment.tier is QualificationTier.PRIORITY
    assert len(assessment.intent.active_signals) == 2


def test_repeated_signal_type_is_not_treated_as_independent_evidence():
    assessment = qualify_prospect(
        prospect_for(company()),
        profile(),
        intent_signals=(
            signal(IntentSignalType.HIRING),
            signal(IntentSignalType.HIRING),
        ),
        now=NOW,
    )

    assert assessment.intent.distinct_signal_types == 1
    assert assessment.intent.strength is IntentStrength.WEAK


def test_stale_and_expired_signals_are_discarded():
    assessment = qualify_prospect(
        prospect_for(company()),
        profile(),
        intent_signals=(
            signal(IntentSignalType.HIRING, observed_at=NOW - timedelta(days=200)),
            signal(
                IntentSignalType.EXPANSION,
                observed_at=NOW - timedelta(days=2),
                expires_at=NOW - timedelta(hours=1),
            ),
        ),
        intent_policy=IntentPolicy(window_days=90),
        now=NOW,
    )

    assert assessment.intent.active_signals == ()
    assert assessment.intent.stale_or_expired_signals == 2
    assert assessment.intent.strength is IntentStrength.NONE


def test_signal_timestamp_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        signal(IntentSignalType.HIRING, observed_at=datetime(2026, 11, 10))


def test_confidence_rewards_independent_and_recent_sources():
    old_single = assess_confidence(
        company(evidence=(evidence(collected_at=NOW - timedelta(days=400)),)), now=NOW
    )
    fresh_multiple = assess_confidence(
        company(
            evidence=(
                evidence(source_id="registry", source_type="public_registry"),
                evidence(source_id="directory", source_type="public_directory"),
            )
        ),
        now=NOW,
    )

    assert fresh_multiple.score > old_single.score
    assert fresh_multiple.distinct_source_count == 2
    assert fresh_multiple.distinct_source_type_count == 2
