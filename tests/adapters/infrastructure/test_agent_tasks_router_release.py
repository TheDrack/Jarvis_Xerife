from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.agent_tasks import create_agent_tasks_router
from app.application.services.agent_task_queue_service import (
    AgentTaskQueueService, TaskQueueUnavailable,
)


def build_client(monkeypatch, release_stub):
    """Router wired to a fake Postgres adapter; the RPC call itself is stubbed."""
    monkeypatch.delenv("JARVIS_TASK_QUEUE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(AgentTaskQueueService, "release", release_stub)

    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(adapter, lambda: SimpleNamespace(id="test-user"))
    )
    return TestClient(app)


def test_release_returns_accepted_and_forwards_attempt_scope(monkeypatch):
    calls = []

    def release_stub(self, task_id, agent_id, attempt_id, reason="worker error"):
        calls.append((task_id, agent_id, attempt_id, reason))
        return True

    client = build_client(monkeypatch, release_stub)
    response = client.post(
        "/v1/agent-tasks/task-9/release",
        json={
            "agent_id": "mini-1",
            "attempt_id": "00000000-0000-0000-0000-000000000009",
            "reason": "provider dropped",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"released": True, "task_id": "task-9"}
    assert calls == [(
        "task-9",
        "mini-1",
        "00000000-0000-0000-0000-000000000009",
        "provider dropped",
    )]


def test_stale_or_foreign_attempt_is_a_conflict_not_a_silent_success(monkeypatch):
    def release_stub(self, *args, **kwargs):
        return False

    client = build_client(monkeypatch, release_stub)
    response = client.post(
        "/v1/agent-tasks/task-9/release",
        json={
            "agent_id": "mini-2",
            "attempt_id": "00000000-0000-0000-0000-000000000009",
        },
    )

    assert response.status_code == 409
    assert "stale" in response.json()["detail"]


def test_queue_unavailable_surfaces_as_503(monkeypatch):
    def release_stub(self, *args, **kwargs):
        raise TaskQueueUnavailable("shared queue requires PostgreSQL")

    client = build_client(monkeypatch, release_stub)
    response = client.post(
        "/v1/agent-tasks/task-9/release",
        json={
            "agent_id": "mini-1",
            "attempt_id": "00000000-0000-0000-0000-000000000009",
        },
    )

    assert response.status_code == 503


def test_release_requires_agent_and_attempt(monkeypatch):
    def release_stub(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("validation must reject the request first")

    client = build_client(monkeypatch, release_stub)
    response = client.post("/v1/agent-tasks/task-9/release", json={"agent_id": "mini-1"})

    assert response.status_code == 422
