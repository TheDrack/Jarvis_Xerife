"""The HUD roadmap endpoint reports verified Cognitive Roadmap evidence."""

from app.adapters.infrastructure.routers.utility import create_utility_router
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_roadmap_progress_uses_verified_status_ledger():
    router = create_utility_router(db_adapter=None, get_current_user=lambda: object())
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/v1/roadmap/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["completion_percentage"] == 75.0
    assert body["progress_unit"] == "roadmap_criteria"
    assert body["progress_scope"] == "currently_mapped_criteria"
    assert body["total_criteria"] == 4
    assert body["completed_criteria"] == 3
    assert body["total_missions"] == 4
    assert body["completed"] == 3
    assert body["planned"] == 1
    assert body["blocked"] == 0
    assert body["status"] == "ready"
    assert body["next_mission"]["criterion_id"] == "C1-WORLD-MODEL"
    assert body["hold_reason"] is None


def test_health_detail_uses_evidence_based_roadmap_metrics(monkeypatch):
    from app.adapters.infrastructure.routers.health import create_health_router
    from app.core.nexus import nexus

    monkeypatch.setattr(nexus, "list_loaded_ids", lambda: [])
    monkeypatch.setattr(nexus, "get_cached_instance", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(create_health_router(db_adapter=None, get_current_user=None))

    response = TestClient(app).get("/v1/health/detail")

    assert response.status_code == 200
    evolution = response.json()["evolution"]
    assert evolution["status"] == "ready"
    assert evolution["roadmap"]["total_criteria"] == 4
    assert evolution["roadmap"]["completed_criteria"] == 3
    assert evolution["roadmap"]["next_mission"]["criterion_id"] == "C1-WORLD-MODEL"
    assert evolution["legacy_inventory"]["is_completion_evidence"] is False
