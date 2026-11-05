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


class OsirisSourceWithObservations(OsirisSource):
    def collect_observations(self, limit: int) -> IntelligenceBatch:
        observation = IntelligenceObservation(
            observation_id="osiris-camera-1",
            source_id="osiris_cctv",
            entity_type="camera",
            entity_id="camera-1",
            observed_at=datetime.now(timezone.utc),
            position=GeoPoint(latitude=-27.5, longitude=-48.5),
            evidence=(
                IntelligenceEvidence(
                    source_id="osiris_cctv",
                    source_name="OSIRIS public camera directory",
                    url="https://osiris.example/cameras",
                    license_or_terms="directory metadata only",
                ),
            ),
        )
        return IntelligenceBatch(
            observations=(observation,),
            sources=(SourceHealth(source_id="osiris_cctv", available=True),),
        )


class OsirisSourceWithBrokenObservations(OsirisSourceWithObservations):
    def collect_observations(self, limit: int) -> IntelligenceBatch:
        raise RuntimeError("private observation endpoint details")


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
        "osiris_observations",
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


@pytest.mark.asyncio
async def test_live_collector_ingests_osiris_observations_alongside_events():
    report = await collect_live_intelligence(
        limit=10,
        public_source=PublicSource(),
        osiris_source=OsirisSourceWithObservations(),
    )

    assert any(event.source_id == "osiris" for event in report.events)
    cameras = [item for item in report.observations if item.source_id == "osiris_cctv"]
    assert len(cameras) == 1
    assert cameras[0].entity_type == "camera"
    assert cameras[0].position == GeoPoint(latitude=-27.5, longitude=-48.5)
    assert any(source.source_id == "osiris_cctv" and source.available for source in report.sources)


@pytest.mark.asyncio
async def test_osiris_observation_failure_does_not_discard_successful_events():
    report = await collect_live_intelligence(
        limit=10,
        public_source=PublicSource(),
        osiris_source=OsirisSourceWithBrokenObservations(),
    )

    assert any(event.source_id == "osiris" for event in report.events)
    assert not any(item.source_id == "osiris_cctv" for item in report.observations)
    failed = next(source for source in report.sources if source.source_id == "osiris_observations")
    assert failed.available is False
    assert failed.error_code == "RUNTIME_ERROR"
    assert "private observation endpoint details" not in str(report.model_dump(mode="json"))
