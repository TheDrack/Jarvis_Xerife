from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.agent_worker_credentials import AgentWorkerCredentialStore
from app.adapters.infrastructure.routers import agent_tasks
from app.application.services.agent_task_queue_service import AgentTaskQueueService


@pytest.mark.parametrize(
    "database_url",
    [
        "postgres://worker:secret@db.example:5432/jarvis",
        "postgresql://worker:secret@db.example:5432/jarvis",
    ],
)
def test_worker_queue_uses_installed_psycopg2_driver(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("JARVIS_TASK_QUEUE_DATABASE_URL", raising=False)

    created = {}
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def create_engine(database_url, **kwargs):
        created["url"] = database_url
        created["kwargs"] = kwargs
        return engine

    worker = SimpleNamespace(
        agent_id="termux-worker",
        principal_id="worker:termux-worker",
        available_tools=("text_reasoning",),
    )
    monkeypatch.setattr(agent_tasks, "create_engine", create_engine)
    monkeypatch.setattr(
        AgentWorkerCredentialStore,
        "authenticate",
        lambda self, token: worker,
    )
    monkeypatch.setattr(
        AgentTaskQueueService,
        "heartbeat",
        lambda self, **kwargs: {"agent_id": kwargs["agent_id"], "status": "available"},
    )

    app = FastAPI()
    app.include_router(agent_tasks.create_agent_tasks_router(None, lambda: None))
    response = TestClient(app).post(
        "/v1/agents/heartbeat",
        headers={"X-Jarvis-Worker-Token": "jarvisw_test-token"},
        json={"agent_id": "termux-worker"},
    )

    assert response.status_code == 200
    assert created["url"].startswith("postgresql+psycopg2://")
    assert created["kwargs"] == {"pool_pre_ping": True, "pool_recycle": 300}
