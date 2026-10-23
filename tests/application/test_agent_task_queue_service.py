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
