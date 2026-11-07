from types import SimpleNamespace
from unittest.mock import Mock

from app.adapters.infrastructure.routers.agent_tasks import _emit_proactive_task_signal


def test_blocked_task_signal_uses_authenticated_owner_identity(monkeypatch):
    assistant = SimpleNamespace(on_event=Mock())
    monkeypatch.setattr(
        "app.adapters.infrastructure.routers.agent_tasks.nexus.resolve",
        lambda component_id: assistant if component_id == "assistant_service" else None,
    )
    user = SimpleNamespace(user_id="owner-123", username="owner@example.test")

    emitted = _emit_proactive_task_signal(
        user,
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
        SimpleNamespace(user_id=None, username=None),
        "task_blocked",
        task_id="task-42",
        result={},
    )

    assert emitted is False
    assistant.on_event.assert_not_called()
