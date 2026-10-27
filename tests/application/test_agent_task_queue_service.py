from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.application.services.agent_task_queue_service import (
    AgentTaskQueueService, TaskQueueUnavailable,
)


def test_queue_rejects_sqlite_without_touching_database():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    service = AgentTaskQueueService(engine)
    with pytest.raises(TaskQueueUnavailable):
        service.claim_next("chatgpt")


def test_priority_validation_is_explicit_before_database_call():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    service.engine.begin = MagicMock(side_effect=AssertionError("DB must not be called"))
    with pytest.raises(ValueError, match="priority"):
        service.enqueue("task-1", "test", priority=1001)


def test_max_attempts_validation_is_explicit_before_database_call():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    service.engine.begin = MagicMock(side_effect=AssertionError("DB must not be called"))
    with pytest.raises(ValueError, match="max_attempts"):
        service.enqueue("task-1", "test", max_attempts=0)


def test_empty_agent_id_is_rejected_before_database_call():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    service.engine.begin = MagicMock(side_effect=AssertionError("DB must not be called"))
    with pytest.raises(ValueError, match="agent_id"):
        service.heartbeat("")



def test_heartbeat_persists_model_provider_and_refreshes_presence():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one.return_value = {
        "agent_id": "runtime-test",
        "status": "available",
        "active_tasks": 0,
        "concurrency_limit": 1,
        "last_seen_at": "now",
    }
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine.begin = MagicMock(return_value=transaction)

    result = service.heartbeat(
        agent_id="runtime-test",
        model_provider="Venice",
        available_tools=["llm.chat", "jarvis.queue"],
    )

    statement = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert "model_provider" in statement
    assert params["model_provider"] == "venice"
    assert params["agent_id"] == "runtime-test"
    assert params["available_tools"] == '["llm.chat", "jarvis.queue"]'
    assert result["agent_id"] == "runtime-test"
