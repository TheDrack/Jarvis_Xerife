from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.application.services.intelligence_core import IntelligenceCore
from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceObservation,
)


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def make_observation(
    entity_id: str,
    *,
    source_id: str = "gods_eye_view",
    entity_type: str = "aircraft",
    observed_at: datetime = NOW,
    altitude_m: int = 9000,
) -> IntelligenceObservation:
    evidence = IntelligenceEvidence(
        source_id=source_id,
        source_name="God's Eye View",
        url="https://github.com/bilawalsidhu/gods-eye-view",
        collected_at=observed_at,
        license_or_terms="Provider source attribution; underlying dataset terms apply",
    )
    return IntelligenceObservation(
        observation_id=f"{source_id}:{entity_type}:{entity_id}:{observed_at.isoformat()}",
        source_id=source_id,
        entity_type=entity_type,
        entity_id=entity_id,
        observed_at=observed_at,
        position={"latitude": 40.0, "longitude": -73.0},
        attributes={"altitude_m": altitude_m, "callsign": "TEST123"},
        evidence=(evidence,),
    )


def test_core_preserves_observations_separately_from_discrete_events():
    observation = make_observation("abc123")
    report = IntelligenceCore().process(
        IntelligenceBatch(observations=(observation,))
    )

    assert report.events == ()
    assert report.observations == (observation,)
    assert report.input_event_count == 0
    assert report.unique_event_count == 0
    assert report.duplicate_event_count == 0
    assert report.input_observation_count == 1
    assert report.unique_observation_count == 1
    assert report.duplicate_observation_count == 0


def test_core_deduplicates_exact_entity_snapshot_identity():
    observation = make_observation("abc123")
    report = IntelligenceCore().process(
        IntelligenceBatch(observations=(observation, observation))
    )

    assert report.observations == (observation,)
    assert report.input_observation_count == 2
    assert report.unique_observation_count == 1
    assert report.duplicate_observation_count == 1


def test_conflicting_same_time_observation_is_input_order_independent():
    lower = make_observation("abc123", altitude_m=8000)
    higher = make_observation("abc123", altitude_m=10000)
    core = IntelligenceCore()

    forward = core.process(IntelligenceBatch(observations=(lower, higher)))
    reverse = core.process(IntelligenceBatch(observations=(higher, lower)))

    assert forward.observations == reverse.observations
    assert forward.observations[0].attributes == reverse.observations[0].attributes


def test_different_observation_times_are_retained_as_history():
    earlier = make_observation("abc123", observed_at=NOW)
    later = make_observation(
        "abc123",
        observed_at=NOW + timedelta(minutes=1),
        altitude_m=9500,
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(observations=(later, earlier))
    )

    assert len(report.observations) == 2
    assert [item.observed_at for item in report.observations] == [NOW, NOW + timedelta(minutes=1)]
    assert report.unique_observation_count == 2
    assert report.duplicate_observation_count == 0


def test_different_entities_and_providers_are_never_merged():
    observations = (
        make_observation("abc123"),
        make_observation("xyz987"),
        make_observation("abc123", source_id="osiris"),
    )

    report = IntelligenceCore().process(
        IntelligenceBatch(observations=observations)
    )

    assert len(report.observations) == 3
    assert {item.source_id for item in report.observations} == {
        "gods_eye_view",
        "osiris",
    }


def test_observation_attributes_are_bounded_and_finite():
    base = make_observation("abc123").model_dump()

    too_many = dict(base, attributes={f"field_{i}": i for i in range(65)})
    with pytest.raises(ValidationError):
        IntelligenceObservation.model_validate(too_many)

    non_finite = dict(base, attributes={"altitude": float("nan")})
    with pytest.raises(ValidationError):
        IntelligenceObservation.model_validate(non_finite)

    oversized = dict(base, attributes={"description": "x" * 1001})
    with pytest.raises(ValidationError):
        IntelligenceObservation.model_validate(oversized)


def test_observation_requires_at_least_one_provenance_record():
    base = make_observation("abc123").model_dump()
    invalid = dict(base, evidence=())

    with pytest.raises(ValidationError):
        IntelligenceObservation.model_validate(invalid)
