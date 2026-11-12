"""Regression tests for the authenticated mission execution boundary."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.api_models import User
from app.adapters.infrastructure.routers.missions import create_missions_router
from app.application.services.task_runner import TaskRunner


def _authenticated_user() -> User:
    return User(username="mission-test", user_id="mission-test-user")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_missions_router(_authenticated_user))
    return TestClient(app)


def test_mission_endpoint_fails_closed_without_hardened_executor(monkeypatch):
    """The API must not run submitted Python through the host TaskRunner."""
    def forbidden_host_execution(self, mission):
        raise AssertionError("untrusted mission reached the host TaskRunner")

    monkeypatch.setattr(TaskRunner, "execute_mission", forbidden_host_execution)

    response = _client().post(
        "/v1/missions/execute",
        json={
            "mission_id": "untrusted-mission",
            "code": "print('this must never run')",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Isolated mission execution is unavailable"


def test_mission_endpoint_requires_authentication():
    """The fail-closed behavior must not make the protected endpoint public."""
    app = FastAPI()
    app.include_router(create_missions_router(lambda: None))
    client = TestClient(app)

    # The supplied dependency is intentionally replaced with an auth failure.
    from fastapi import HTTPException

    def reject_unauthenticated_request():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[lambda: None] = reject_unauthenticated_request
    response = client.post(
        "/v1/missions/execute",
        json={"mission_id": "unauthenticated", "code": "print('no')"},
    )

    assert response.status_code == 401
