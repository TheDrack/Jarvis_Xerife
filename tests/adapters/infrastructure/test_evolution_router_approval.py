"""Authenticated proposal approval API tests."""
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.api_models import User
from app.adapters.infrastructure.routers.evolution import create_evolution_router
from app.application.services.strategist_service import StrategistService
from app.core.nexus import nexus
from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
)
from app.utils.document_store import document_store


def _pending_proposal(service: StrategistService) -> Path:
    matrix = service.generate_viability_matrix(
        proposal_title="Authenticated Approval",
        proposal_description="Persist the identity of the authenticated human.",
        cost=CostEstimate(api_cost_usd=1.0),
        impact=ImpactEstimate(user_utility_level=ImpactLevel.HIGH),
        risk=RiskEstimate(risk_level=RiskLevel.LOW),
    )
    return service.archive_proposal(matrix)


def test_approval_route_records_authenticated_user_and_dispatches_audit_data(
    monkeypatch, tmp_path
):
    service = StrategistService(proposals_dir=tmp_path)
    pending_path = _pending_proposal(service)

    class RecordingWorker:
        def __init__(self):
            self.events = []

        def trigger_repository_dispatch(self, *, event_type, client_payload):
            self.events.append((event_type, client_payload))
            return True

    worker = RecordingWorker()
    monkeypatch.setattr(
        "app.application.services.strategist_service.StrategistService",
        lambda: service,
    )
    monkeypatch.setattr(
        nexus,
        "resolve",
        lambda name: worker if name == "github_worker" else None,
    )

    def authenticated_user():
        return User(username="commander", user_id="user-123")

    app = FastAPI()
    app.include_router(
        create_evolution_router(
            db_adapter=SimpleNamespace(engine=None),
            get_current_user=authenticated_user,
        )
    )

    response = TestClient(app).post(
        f"/v1/proposals/{pending_path.name}/approve"
    )

    assert response.status_code == 200
    assert response.json()["approved_by"] == "user-123"
    approved_path = service.approved_dir / pending_path.name
    approval = document_store.read(approved_path)
    assert approval["approved_by"] == "user-123"
    assert approval["approved"] is True
    assert approval["status"] == "approved"
    assert worker.events[0][0] == "implement_proposal"
    assert worker.events[0][1]["approved_by"] == "user-123"
    assert worker.events[0][1]["approved_at"] == approval["approved_at"]


def test_approval_route_fails_closed_without_authentication_dependency(monkeypatch):
    def forbidden_service_construction():
        raise AssertionError("approval service must not be called without auth")

    monkeypatch.setattr(
        "app.application.services.strategist_service.StrategistService",
        forbidden_service_construction,
    )
    app = FastAPI()
    app.include_router(create_evolution_router(db_adapter=SimpleNamespace(engine=None)))

    response = TestClient(app).post("/v1/proposals/any.jrvs/approve")

    assert response.status_code == 503
    assert "authentication" in response.json()["detail"].lower()


def test_approval_route_rejects_authenticated_user_without_stable_identity():
    def anonymous_user():
        return User(username="", user_id=None)

    app = FastAPI()
    app.include_router(
        create_evolution_router(
            db_adapter=SimpleNamespace(engine=None),
            get_current_user=anonymous_user,
        )
    )

    response = TestClient(app).post("/v1/proposals/any.jrvs/approve")

    assert response.status_code == 401
    assert "identity" in response.json()["detail"].lower()
