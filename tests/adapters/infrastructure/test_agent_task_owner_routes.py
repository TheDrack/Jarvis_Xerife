from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.agent_tasks import create_agent_tasks_router
from app.application.services.agent_task_queue_service import AgentTaskQueueService


def _client(user):
    adapter = SimpleNamespace(
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, lambda: user))
    return TestClient(app)


def test_enqueue_derives_owner_and_creator_from_auth_adapter_mapping(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        AgentTaskQueueService,
        "enqueue",
        lambda self, **kwargs: captured.update(kwargs) or {"task_id": kwargs["task_id"]},
    )
    client = _client({"user_id": "owner-1", "username": "owner@example.test"})

    response = client.post(
        "/v1/agent-tasks",
        json={
            "task_id": "task-1",
            "objective": "Owned task",
            "owner_id": "attacker",
            "created_by": "attacker",
        },
    )

    assert response.status_code == 200
    assert captured["owner_id"] == "owner-1"
    assert captured["created_by"] == "owner-1"


def test_legacy_environment_admin_uses_stable_local_principal(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        AgentTaskQueueService,
        "enqueue",
        lambda self, **kwargs: captured.update(kwargs) or {"task_id": kwargs["task_id"]},
    )
    client = _client({"user_id": "", "username": "admin", "email": "admin@jarvis.local"})

    response = client.post(
        "/v1/agent-tasks",
        json={"task_id": "admin-task", "objective": "Admin task"},
    )

    assert response.status_code == 200
    assert captured["owner_id"] == captured["created_by"] == "local-admin"


def test_mutable_username_is_not_accepted_as_owner_identity(monkeypatch):
    called = False

    def enqueue_stub(self, **kwargs):
        nonlocal called
        called = True
        return {"task_id": kwargs["task_id"]}

    monkeypatch.setattr(AgentTaskQueueService, "enqueue", enqueue_stub)
    client = _client({"user_id": "", "username": "mutable-name@example.test"})

    response = client.post(
        "/v1/agent-tasks",
        json={"task_id": "task-no-owner", "objective": "Must reject unstable identity"},
    )

    assert response.status_code == 401
    assert called is False


def test_routine_creation_derives_owner_from_authenticated_principal(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        AgentTaskQueueService,
        "create_routine",
        lambda self, **kwargs: captured.update(kwargs) or {"routine_key": kwargs["routine_key"]},
    )
    client = _client({"user_id": "owner-2"})

    response = client.post(
        "/v1/routines",
        json={
            "routine_key": "daily-owner-check",
            "name": "Daily owner check",
            "owner_id": "attacker",
            "created_by": "attacker",
        },
    )

    assert response.status_code == 200
    assert captured["owner_id"] == captured["created_by"] == "owner-2"


def test_routine_trigger_passes_authenticated_owner_to_service(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        AgentTaskQueueService,
        "trigger_routine",
        lambda self, routine_key, run_key, *, owner_id=None: (
            captured.update(routine_key=routine_key, run_key=run_key, owner_id=owner_id)
            or {"routine_key": routine_key}
        ),
    )
    client = _client({"user_id": "owner-3"})

    response = client.post(
        "/v1/routines/shared-daily/trigger",
        json={"run_key": "2026-11-08"},
    )

    assert response.status_code == 200
    assert captured == {
        "routine_key": "shared-daily",
        "run_key": "2026-11-08",
        "owner_id": "owner-3",
    }
