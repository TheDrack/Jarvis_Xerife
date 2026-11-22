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



def test_worker_cannot_finish_as_another_agent(monkeypatch):
    def finish_stub(self, *args, **kwargs):
        raise AssertionError("impersonated finish must not reach the queue")

    monkeypatch.setattr(AgentTaskQueueService, "finish", finish_stub)
    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    client = _client(monkeypatch, worker, heartbeat_stub=lambda self, **kwargs: {})

    response = client.post(
        "/v1/agent-tasks/task-1/finish",
        json={
            "agent_id": "victim-agent",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "result": {},
        },
    )

    assert response.status_code == 403


def test_worker_cannot_release_as_another_agent(monkeypatch):
    def release_stub(self, *args, **kwargs):
        raise AssertionError("impersonated release must not reach the queue")

    monkeypatch.setattr(AgentTaskQueueService, "release", release_stub)
    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    client = _client(monkeypatch, worker, heartbeat_stub=lambda self, **kwargs: {})

    response = client.post(
        "/v1/agent-tasks/task-1/release",
        json={
            "agent_id": "victim-agent",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "reason": "test",
        },
    )

    assert response.status_code == 403


def test_worker_heartbeat_does_not_require_user_jwt(monkeypatch):
    from fastapi import HTTPException

    calls = []
    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    monkeypatch.setattr(
        AgentTaskQueueService,
        "heartbeat",
        lambda self, **kwargs: calls.append(kwargs) or {"status": "available"},
    )
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))

    def reject_user():
        raise HTTPException(status_code=401, detail="JWT must not be needed by a worker")

    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, reject_user, get_current_worker=lambda: worker))
    response = TestClient(app).post(
        "/v1/agents/heartbeat",
        json={"agent_id": "trusted-mini-1", "available_tools": ["text_reasoning"]},
    )

    assert response.status_code == 200
    assert calls[0]["agent_id"] == "trusted-mini-1"


def test_enqueue_still_requires_user_jwt():
    from fastapi import HTTPException

    def reject_user():
        raise HTTPException(status_code=401, detail="Not authenticated")

    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, reject_user))
    response = TestClient(app).post(
        "/v1/agent-tasks",
        json={"task_id": "task-user-1", "objective": "Owner-created task"},
    )

    assert response.status_code == 401


def test_worker_inference_uses_server_handler_without_user_jwt(monkeypatch):
    from fastapi import HTTPException

    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    captured = []

    def inference_handler(message):
        captured.append(message)
        return {"success": True, "output": "server-side inference"}

    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks._build_remote_inference_handler",
        lambda: inference_handler,
        raising=False,
    )
    monkeypatch.setattr(AgentTaskQueueService, "owns_active_attempt", lambda self, *args: True)

    def reject_user():
        raise HTTPException(status_code=401, detail="JWT must not be needed by a worker")

    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, reject_user, get_current_worker=lambda: worker))
    response = TestClient(app).post(
        "/v1/agent-inference/complete",
        json={
            "agent_id": "trusted-mini-1",
            "task_id": "task-inference-1",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "objective": "Analyze this task",
            "task_type": "analysis",
            "context": "Only supplied context",
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["output"] == "server-side inference"
    assert captured[0].payload["objective"] == "Analyze this task"


def test_worker_inference_rejects_agents_without_text_reasoning():
    worker = SimpleNamespace(
        agent_id="tool-less-worker",
        principal_id="worker:tool-less-worker",
        available_tools=(),
    )
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(
            adapter,
            lambda: SimpleNamespace(user_id="unused"),
            get_current_worker=lambda: worker,
        )
    )
    response = TestClient(app).post(
        "/v1/agent-inference/complete",
        json={"agent_id": "tool-less-worker", "task_id": "task-1", "attempt_id": "00000000-0000-0000-0000-000000000001", "objective": "Analyze"},
    )

    assert response.status_code == 403


def test_claim_finish_and_release_do_not_require_user_jwt(monkeypatch):
    from fastapi import HTTPException

    worker = SimpleNamespace(
        agent_id="trusted-mini-1",
        principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    monkeypatch.setattr(AgentTaskQueueService, "claim_next", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(AgentTaskQueueService, "owns_active_attempt", lambda self, *args: True)
    monkeypatch.setattr(AgentTaskQueueService, "finish", lambda self, *args, **kwargs: True)
    monkeypatch.setattr(AgentTaskQueueService, "release", lambda self, *args, **kwargs: True)

    def reject_user():
        raise HTTPException(status_code=401, detail="Worker must not need a user JWT")

    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, reject_user, get_current_worker=lambda: worker))
    client = TestClient(app)
    headers = {"Content-Type": "application/json"}

    claim = client.post(
        "/v1/agent-tasks/claim-next", headers=headers,
        json={"agent_id": "trusted-mini-1", "lease_seconds": 90},
    )
    finish = client.post(
        "/v1/agent-tasks/task-1/finish", headers=headers,
        json={"agent_id": "trusted-mini-1", "attempt_id": "attempt-1", "status": "completed", "result": {}},
    )
    release = client.post(
        "/v1/agent-tasks/task-2/release", headers=headers,
        json={"agent_id": "trusted-mini-1", "attempt_id": "attempt-2", "reason": "retry"},
    )

    assert (claim.status_code, finish.status_code, release.status_code) == (200, 200, 200)


def test_remote_inference_failure_does_not_leak_provider_exception(monkeypatch):
    from fastapi import HTTPException

    worker = SimpleNamespace(
        agent_id="trusted-mini-1", principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )

    def fail_handler():
        def fail(_message):
            raise RuntimeError("private-provider-secret-value")
        return fail

    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks._build_remote_inference_handler",
        fail_handler,
    )
    monkeypatch.setattr(AgentTaskQueueService, "owns_active_attempt", lambda self, *args: True)
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(
            adapter, lambda: (_ for _ in ()).throw(HTTPException(status_code=401)),
            get_current_worker=lambda: worker,
        )
    )
    response = TestClient(app).post(
        "/v1/agent-inference/complete",
        json={"agent_id": "trusted-mini-1", "task_id": "task-1", "attempt_id": "00000000-0000-0000-0000-000000000001", "objective": "Analyze"},
    )

    assert response.status_code == 503
    assert "private-provider-secret-value" not in response.text


def test_worker_cannot_infer_against_a_stale_or_foreign_attempt(monkeypatch):
    worker = SimpleNamespace(
        agent_id="trusted-mini-1", principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    monkeypatch.setattr(AgentTaskQueueService, "owns_active_attempt", lambda self, *args: False)
    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks._build_remote_inference_handler",
        lambda: (_ for _ in ()).throw(AssertionError("stale attempt must not invoke provider")),
    )
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(
            adapter, lambda: SimpleNamespace(user_id="unused"),
            get_current_worker=lambda: worker,
        )
    )

    response = TestClient(app).post(
        "/v1/agent-inference/complete",
        json={
            "agent_id": "trusted-mini-1", "task_id": "task-1",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "objective": "Analyze",
        },
    )

    assert response.status_code == 409


def test_worker_renews_its_lease_without_user_jwt(monkeypatch):
    from fastapi import HTTPException

    worker = SimpleNamespace(
        agent_id="trusted-mini-1", principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    calls = []
    monkeypatch.setattr(
        AgentTaskQueueService, "renew_lease",
        lambda self, *args: calls.append(args) or True,
    )
    def reject_user():
        raise HTTPException(status_code=401, detail="worker JWT must not be required")

    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, reject_user, get_current_worker=lambda: worker))
    response = TestClient(app).post(
        "/v1/agent-tasks/task-1/renew",
        json={
            "agent_id": "trusted-mini-1",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "lease_seconds": 120,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"renewed": True, "task_id": "task-1"}
    assert calls == [("task-1", "trusted-mini-1", "00000000-0000-0000-0000-000000000001", 120)]


def test_worker_cannot_renew_another_agents_lease():
    worker = SimpleNamespace(
        agent_id="trusted-mini-1", principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, lambda: None, get_current_worker=lambda: worker))
    response = TestClient(app).post(
        "/v1/agent-tasks/task-1/renew",
        json={
            "agent_id": "other-agent",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 403


def test_worker_cannot_finish_after_lease_expiry(monkeypatch):
    worker = SimpleNamespace(
        agent_id="trusted-mini-1", principal_id="worker:trusted-mini-1",
        available_tools=("text_reasoning",),
    )
    monkeypatch.setattr(AgentTaskQueueService, "owns_active_attempt", lambda self, *args: False)
    monkeypatch.setattr(
        AgentTaskQueueService, "finish",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale finish must not reach DB RPC")),
    )
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    app = FastAPI()
    app.include_router(create_agent_tasks_router(adapter, lambda: None, get_current_worker=lambda: worker))
    response = TestClient(app).post(
        "/v1/agent-tasks/task-1/finish",
        json={
            "agent_id": "trusted-mini-1",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "status": "completed",
            "result": {"success": True},
        },
    )

    assert response.status_code == 409
