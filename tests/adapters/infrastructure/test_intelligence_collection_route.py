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
    assert response.json()["report"]["events"][0]["title"] == "Real fixture event"
    assert response.json()["history"] == {"status": "disabled", "reason": "feature_flag_disabled"}


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



def test_collect_endpoint_persists_only_when_explicitly_enabled(monkeypatch):
    calls = []
    class Repository:
        def persist(self, report):
            calls.append(report)
    async def collector(*, limit):
        return make_report()
    monkeypatch.setenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "true")
    app = FastAPI()
    app.include_router(create_intelligence_dashboard_router(
        lambda: {"username": "operator"}, collector=collector, history_repository=Repository()
    ))
    response = TestClient(app).post("/v1/intelligence/collect?limit=10")
    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json()["history"] == {"status": "persisted", "reason": None}


def test_history_write_failure_does_not_discard_live_collection(monkeypatch):
    class BrokenRepository:
        def persist(self, report):
            raise RuntimeError("private database details")
    async def collector(*, limit):
        return make_report()
    monkeypatch.setenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "true")
    app = FastAPI()
    app.include_router(create_intelligence_dashboard_router(
        lambda: {"username": "operator"}, collector=collector, history_repository=BrokenRepository()
    ))
    response = TestClient(app).post("/v1/intelligence/collect?limit=10")
    assert response.status_code == 200
    assert response.json()["report"]["events"][0]["title"] == "Real fixture event"
    assert response.json()["history"] == {"status": "unavailable", "reason": "persistence_failed"}
    assert "private database details" not in response.text
