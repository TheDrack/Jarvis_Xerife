from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.intelligence_dashboard import (
    create_intelligence_dashboard_router,
)
from app.domain.intelligence.contracts import (
    IntelligenceEvent,
    IntelligenceEvidence,
    IntelligenceReport,
    SourceHealth,
)


def make_report():
    evidence = IntelligenceEvidence(
        source_id="fixture",
        source_name="Fixture",
        url="https://example.com/event",
        license_or_terms="Fixture terms",
    )
    event = IntelligenceEvent(
        event_id="fixture:1",
        source_id="fixture",
        domain="test",
        category="test",
        title="Real fixture event",
        url="https://example.com/event",
        observed_at=datetime.now(timezone.utc),
        evidence=evidence,
    )
    return IntelligenceReport(
        events=(event,),
        sources=(SourceHealth(source_id="fixture", available=True),),
        input_event_count=1,
        unique_event_count=1,
        duplicate_event_count=0,
    )


def test_collect_endpoint_requires_authenticated_user():
    calls = []
    async def collector(*, limit):
        calls.append(limit)
        return make_report()

    app = FastAPI()
    app.include_router(
        create_intelligence_dashboard_router(
            lambda: {"username": "operator"}, collector=collector
        )
    )
    response = TestClient(app).post("/v1/intelligence/collect?limit=10")

    assert response.status_code == 200
    assert calls == [10]
    assert response.json()["events"][0]["title"] == "Real fixture event"


def test_collect_endpoint_rejects_out_of_range_limit():
    async def collector(*, limit):
        return make_report()

    app = FastAPI()
    app.include_router(
        create_intelligence_dashboard_router(
            lambda: {"username": "operator"}, collector=collector
        )
    )
    response = TestClient(app).post("/v1/intelligence/collect?limit=1000")

    assert response.status_code == 422
