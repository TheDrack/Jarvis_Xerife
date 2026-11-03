from datetime import datetime, timezone

import pytest

from app.application.services.intelligence_collector import collect_live_intelligence
from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceEvidence,
    IntelligenceEvent,
    IntelligenceObservation,
    GeoPoint,
    SourceHealth,
)


def make_event(source_id: str) -> IntelligenceEvent:
    evidence = IntelligenceEvidence(
        source_id=source_id,
        source_name=source_id,
        url=f"https://{source_id}.example/event",
        license_or_terms="test terms",
    )
    return IntelligenceEvent(
        event_id=f"{source_id}:1",
        source_id=source_id,
        domain="test",
        category="news",
        title=f"Event from {source_id}",
        url=f"https://{source_id}.example/event",
        evidence=evidence,
    )


class PublicSource:
    def collect_public_events(self, limit: int) -> IntelligenceBatch:
        assert limit == 10
        return IntelligenceBatch(
            events=(make_event("public"),),
            sources=(SourceHealth(source_id="public", available=True),),
        )


class OsirisSource:
    def collect_events(self, limit: int) -> IntelligenceBatch:
        return IntelligenceBatch(
            events=(make_event("osiris"),),
            sources=(SourceHealth(source_id="osiris", available=True),),
        )


class GodsEyeSource:
    async def collect_observations(self) -> IntelligenceBatch:
        observation = IntelligenceObservation(
            observation_id="obs-1",
            source_id="gods_eye_view",
            entity_type="aircraft",
            entity_id="abc123",
            observed_at=datetime.now(timezone.utc),
            position=GeoPoint(latitude=-27.5, longitude=-48.5),
            evidence=(
                IntelligenceEvidence(
                    source_id="gods_eye_view",
                    source_name="God's Eye",
                    url="https://example.com/source",
                    license_or_terms="test terms",
                ),
            ),
        )
        return IntelligenceBatch(
            observations=(observation,),
            sources=(SourceHealth(source_id="gods_eye_view", available=True),),
        )


@pytest.mark.asyncio
async def test_live_collector_unifies_events_and_observations_without_persistence():
    report = await collect_live_intelligence(
        limit=10,
        public_source=PublicSource(),
        osiris_source=OsirisSource(),
        gods_eye_source=GodsEyeSource(),
    )

    assert {event.source_id for event in report.events} == {"public", "osiris"}
    assert len(report.observations) == 1
    assert {source.source_id for source in report.sources} == {
        "public",
        "osiris",
        "gods_eye_view",
    }


@pytest.mark.asyncio
async def test_live_collector_preserves_partial_success_when_one_source_fails():
    class BrokenOsiris:
        def collect_events(self, limit: int):
            raise RuntimeError("private upstream details")

    report = await collect_live_intelligence(
        limit=10,
        public_source=PublicSource(),
        osiris_source=BrokenOsiris(),
    )

    assert any(event.source_id == "public" for event in report.events)
    osiris = next(source for source in report.sources if source.source_id == "osiris")
    assert osiris.available is False
    assert osiris.error_code == "RUNTIME_ERROR"
    assert "private upstream details" not in str(report.model_dump(mode="json"))

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]