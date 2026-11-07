from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.agent_worker_credentials import AgentWorkerCredentialStore
from app.adapters.infrastructure.routers.agent_tasks import create_agent_tasks_router
from app.application.services.agent_task_queue_service import AgentTaskQueueService


def _client(monkeypatch, worker, *, heartbeat_stub):
    monkeypatch.delenv("JARVIS_TASK_QUEUE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(AgentTaskQueueService, "heartbeat", heartbeat_stub)
    adapter = SimpleNamespace(
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(
            adapter,
            lambda: SimpleNamespace(user_id="owner-1"),
            get_current_worker=lambda: worker,
        )
    )
    return TestClient(app)


def test_heartbeat_uses_credential_identity_and_server_capabilities(monkeypatch):
    calls = []
    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )

    def heartbeat_stub(self, **kwargs):
        calls.append(kwargs)
        return {"agent_id": kwargs["agent_id"], "status": "available"}

    client = _client(monkeypatch, worker, heartbeat_stub=heartbeat_stub)
    response = client.post(
        "/v1/agents/heartbeat",
        json={
            "agent_id": "trusted-mini-1",
            "available_tools": ["text_reasoning", "shell_execute"],
            "concurrency_limit": 64,
            "model_provider": "groq",
        },
    )

    assert response.status_code == 200
    assert calls == [{
        "agent_id": "trusted-mini-1",
        "runtime_version": "unknown",
        "environment": "unknown",
        "model_provider": "groq",
        "available_tools": ["text_reasoning"],
        "status": "available",
        "concurrency_limit": 1,
        "estimated_cost": 0,
        "coordination_cost": 0,
        "estimated_latency_seconds": 0,
    }]


def test_worker_cannot_impersonate_another_agent_in_heartbeat(monkeypatch):
    def heartbeat_stub(self, **kwargs):
        raise AssertionError("impersonated heartbeat must not reach the queue")

    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    client = _client(monkeypatch, worker, heartbeat_stub=heartbeat_stub)

    response = client.post(
        "/v1/agents/heartbeat",
        json={"agent_id": "victim-agent", "available_tools": ["text_reasoning"]},
    )

    assert response.status_code == 403



def test_worker_endpoints_reject_missing_worker_credential(monkeypatch):
    monkeypatch.delenv("JARVIS_TASK_QUEUE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    adapter = SimpleNamespace(
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(adapter, lambda: SimpleNamespace(user_id="owner-1"))
    )

    response = TestClient(app).post(
        "/v1/agents/heartbeat",
        json={"agent_id": "mini-1", "available_tools": ["text_reasoning"]},
    )

    assert response.status_code == 401


def test_worker_endpoints_reject_unknown_worker_credential(monkeypatch):
    monkeypatch.delenv("JARVIS_TASK_QUEUE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(AgentWorkerCredentialStore, "authenticate", lambda self, token: None)
    adapter = SimpleNamespace(
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(adapter, lambda: SimpleNamespace(user_id="owner-1"))
    )

    response = TestClient(app).post(
        "/v1/agents/heartbeat",
        headers={"X-Jarvis-Worker-Token": "jarvisw_unknown-token"},
        json={"agent_id": "mini-1", "available_tools": ["text_reasoning"]},
    )

    assert response.status_code == 401


def test_worker_cannot_claim_as_another_agent(monkeypatch):
    def claim_stub(self, *args, **kwargs):
        raise AssertionError("impersonated claim must not reach the queue")

    monkeypatch.setattr(AgentTaskQueueService, "claim_next", claim_stub)
    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    client = _client(monkeypatch, worker, heartbeat_stub=lambda self, **kwargs: {})

    response = client.post(
        "/v1/agent-tasks/claim-next",
        json={"agent_id": "victim-agent", "lease_seconds": 90},
    )

    assert response.status_code == 403
