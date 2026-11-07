"""Tests for the authenticated Universal Intelligence dashboard."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.intelligence_dashboard import (
    build_intelligence_status,
    collect_live_intelligence,
    create_intelligence_dashboard_router,
)


def _client(user_dependency=None, collector=None):
    app = FastAPI()
    app.include_router(
        create_intelligence_dashboard_router(
            user_dependency or (lambda: {"username": "test-user"}),
            collector=collector or collect_live_intelligence,
        )
    )
    return TestClient(app)


def test_status_endpoint_invokes_authenticated_user_dependency():
    calls = []

    def current_user():
        calls.append("authenticated")
        return {"username": "test-user"}

    response = _client(current_user).get("/v1/intelligence/status")

    assert response.status_code == 200
    assert calls == ["authenticated"]


def test_status_distinguishes_configured_from_probed_services(monkeypatch):
    monkeypatch.setenv(
        "JARVIS_OSIRIS_API_BASE_URL",
        "https://osiris.internal.example/api?token=must-not-leak",
    )
    monkeypatch.delenv("JARVIS_GEV_MCP_ENTRYPOINT", raising=False)

    status = build_intelligence_status()
    sources = {source["id"]: source for source in status["sources"]}

    assert sources["osiris"]["runtime"] == "configured_not_probed"
    assert sources["gods_eye_view"]["runtime"] == "not_configured"
    assert "must-not-leak" not in str(status)
    assert "osiris.internal.example" not in str(status)


def test_status_does_not_fabricate_collection_metrics():
    status = build_intelligence_status()

    assert status["data_plane"]["available"] is False
    assert status["data_plane"]["event_count"] is None
    assert status["data_plane"]["observation_count"] is None
    assert status["data_plane"]["last_collection_at"] is None


def test_worker_status_is_disabled_until_both_feature_flags_are_enabled(monkeypatch):
    monkeypatch.setenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "true")
    monkeypatch.delenv("JARVIS_INTELLIGENCE_WORKER_ENABLED", raising=False)

    status = build_intelligence_status()

    assert status["worker"]["enabled_by_configuration"] is False
    assert status["worker"]["runtime"] == "disabled"
    assert status["worker"]["automatic_retention_deletion"] is False


def test_worker_status_reports_configuration_without_claiming_runtime_health(monkeypatch):
    monkeypatch.setenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "true")
    monkeypatch.setenv("JARVIS_INTELLIGENCE_WORKER_ENABLED", "true")

    status = build_intelligence_status()

    assert status["worker"]["enabled_by_configuration"] is True
    assert status["worker"]["runtime"] == "configured_not_probed"
    assert status["worker"]["worker_migration_file_present"] is True
    assert status["worker"]["interval_seconds"] == 300


def test_status_reports_history_migration_separately_from_remote_application():
    status = build_intelligence_status()

    assert status["history"]["migration_file_present"] is True
    assert status["history"]["remote_migration_state"] == "unverified"
    assert status["history"]["persistence_adapter"] == "implemented"
    assert status["history"]["production_write_performed"] is False


def test_dashboard_page_is_served_from_native_static_assets():
    response = _client().get("/intelligence")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "UNIVERSAL INTELLIGENCE" in response.text
    assert "jarvis_auth_token" in response.text
    assert "/v1/intelligence/status" in response.text
    assert "setInterval(load,15000)" in response.text
    assert "Nenhum evento fictício" in response.text

from pathlib import Path


def test_main_hud_links_to_universal_intelligence():
    repository_root = Path(__file__).resolve().parents[3]
    hud = (repository_root / "app" / "static" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/intelligence"' in hud
    assert "Abrir painel Universal Intelligence" in hud

def test_worker_status_handles_invalid_numeric_configuration(monkeypatch):
    monkeypatch.setenv("JARVIS_INTELLIGENCE_WORKER_INTERVAL_SECONDS", "invalid")
    monkeypatch.setenv("JARVIS_INTELLIGENCE_WORKER_LEASE_SECONDS", "1")

    status = build_intelligence_status()

    assert status["worker"]["interval_seconds"] == 300
    assert status["worker"]["lease_seconds"] == 180


def test_authenticated_collection_endpoint_integrates_sources_core_and_report(
    monkeypatch,
):
    from datetime import datetime, timezone

    from app.application.services.intelligence_collector import (\n        collect_live_intelligence,\n    )
    from app.domain.intelligence.contracts import (
        IntelligenceBatch,
        IntelligenceEvidence,
        IntelligenceEvent,
        SourceHealth,
    )

    monkeypatch.setenv("JARVIS_INTELLIGENCE_HISTORY_ENABLED", "false")
    observed_at = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    def event(event_id, source_id):
        url = "https://publisher.example/shared-story"
        evidence = IntelligenceEvidence(
            source_id=source_id,
            source_name=source_id,
            url=url,
            collected_at=observed_at,
            license_or_terms="test terms",
        )
        return IntelligenceEvent(
            event_id=event_id,
            source_id=source_id,
            domain="science",
            category="news",
            title="Shared intelligence report",
            url=url,
            observed_at=observed_at,
            evidence=evidence,
        )

    class PublicSource:
        def collect_public_events(self, limit):
            assert limit == 10
            duplicate = event("public-1", "gdelt")
            return IntelligenceBatch(
                events=(duplicate, duplicate),
                sources=(SourceHealth(source_id="gdelt", available=True),),
            )

    class OsirisSource:
        def collect_events(self, limit):
            return IntelligenceBatch(
                events=(event("osiris-1", "osiris"),),
                sources=(SourceHealth(source_id="osiris", available=True),),
            )

        def collect_observations(self, limit):
            raise RuntimeError("private OSIRIS endpoint detail")

    class BrokenGodsEyeSource:
        async def collect_observations(self):
            raise TimeoutError("private GEV endpoint detail")

    async def integrated_collector(limit):
        return await collect_live_intelligence(
            limit=limit,
            public_source=PublicSource(),
            osiris_source=OsirisSource(),
            gods_eye_source=BrokenGodsEyeSource(),
        )

    response = _client(collector=integrated_collector).post(
        "/v1/intelligence/collect?limit=10"
    )

    assert response.status_code == 200
    payload = response.json()
    report = payload["report"]
    assert report["input_event_count"] == 3
    assert report["unique_event_count"] == 2
    assert report["duplicate_event_count"] == 1
    assert len(report["correlations"]) == 1
    assert report["correlations"][0]["basis"] == "same_url"
    assert report["correlations"][0]["status"] == "candidate"
    assert {item["source_id"] for item in report["events"]} == {
        "gdelt",
        "osiris",
    }
    source_health = {item["source_id"]: item for item in report["sources"]}
    assert source_health["gdelt"]["available"] is True
    assert source_health["osiris"]["available"] is True
    assert source_health["osiris_observations"]["available"] is False
    assert source_health["gods_eye_view"]["available"] is False
    assert payload["history"] == {
        "status": "disabled",
        "reason": "feature_flag_disabled",
    }
    assert "private OSIRIS endpoint detail" not in response.text
    assert "private GEV endpoint detail" not in response.text
