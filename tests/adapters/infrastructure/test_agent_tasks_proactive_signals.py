from types import SimpleNamespace
from unittest.mock import Mock

from app.adapters.infrastructure.routers.agent_tasks import _emit_proactive_task_signal


def test_blocked_task_signal_uses_authenticated_owner_identity(monkeypatch):
    assistant = SimpleNamespace(on_event=Mock())
    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks.nexus.resolve",
        lambda component_id: assistant if component_id == "assistant_service" else None,
    )
    emitted = _emit_proactive_task_signal(
        "owner-123",
        "task_blocked",
        task_id="task-42",
        result={"objective": "Integrate memory provider", "reason": "Missing credentials"},
    )

    assert emitted is True
    assistant.on_event.assert_called_once_with(
        "task_blocked",
        {
            "user_id": "owner-123",
            "title": "Tarefa bloqueada: task-42",
            "objective": "Integrate memory provider",
            "evidence_ref": "agent-task:task-42",
            "confidence": 0.95,
            "impact": 0.75,
            "urgency": 0.75,
            "availability": 0.9,
            "interruption_cost": 0.15,
        },
    )


def test_task_signal_is_not_emitted_without_authenticated_owner(monkeypatch):
    assistant = SimpleNamespace(on_event=Mock())
    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks.nexus.resolve",
        lambda component_id: assistant if component_id == "assistant_service" else None,
    )

    emitted = _emit_proactive_task_signal(
        None,
        "task_blocked",
        task_id="task-42",
        result={},
    )

    assert emitted is False
    assistant.on_event.assert_not_called()


def test_blocked_task_signal_uses_persisted_task_owner_not_worker_caller(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.adapters.infrastructure.routers.agent_tasks import create_agent_tasks_router
    from app.application.services.agent_task_queue_service import AgentTaskQueueService

    assistant = SimpleNamespace(on_event=Mock())
    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks.nexus.resolve",
        lambda component_id: assistant if component_id == "assistant_service" else None,
    )
    monkeypatch.setattr(AgentTaskQueueService, "finish", lambda self, *args, **kwargs: True)
    monkeypatch.setattr(AgentTaskQueueService, "get_task_owner", lambda self, task_id: "task-owner-7")
    adapter = SimpleNamespace(engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    worker = SimpleNamespace(
        agent_id="mini-worker-1",
        principal_id="worker:mini-worker-1",
        available_tools=("text_reasoning",),
    )
    app = FastAPI()
    app.include_router(
        create_agent_tasks_router(
            adapter,
            lambda: SimpleNamespace(user_id="caller-user-99"),
            get_current_worker=lambda: worker,
        )
    )

    response = TestClient(app).post(
        "/v1/agent-tasks/task-7/finish",
        json={
            "agent_id": "mini-worker-1",
            "attempt_id": "00000000-0000-0000-0000-000000000007",
            "status": "blocked",
            "result": {"objective": "Need user input"},
        },
    )

    assert response.status_code == 200
    assert assistant.on_event.call_args.args[1]["user_id"] == "task-owner-7"
    assert assistant.on_event.call_args.args[1]["user_id"] != "caller-user-99"
