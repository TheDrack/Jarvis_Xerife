"""Tests for the authenticated Universal Intelligence dashboard."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.intelligence_dashboard import (
    build_intelligence_status,
    create_intelligence_dashboard_router,
)


def _client(user_dependency=None):
    app = FastAPI()
    app.include_router(
        create_intelligence_dashboard_router(
            user_dependency or (lambda: {"username": "test-user"})
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


def test_status_reports_history_migration_separately_from_remote_application():
    status = build_intelligence_status()

    assert status["history"]["migration_file_present"] is True
    assert status["history"]["remote_migration_state"] == "unverified"
    assert status["history"]["persistence_adapter"] == "not_implemented"
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
