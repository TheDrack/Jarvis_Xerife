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



def test_release_rejects_empty_identifiers_before_database_call():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    service.engine.begin = MagicMock(side_effect=AssertionError("DB must not be called"))
    with pytest.raises(ValueError, match="attempt_id"):
        service.release("task-1", "mini-1", "  ")


def test_release_calls_the_queue_rpc_with_attempt_scope():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = True
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine.begin = MagicMock(return_value=transaction)

    released = service.release(
        "task-1", "mini-1", "00000000-0000-0000-0000-000000000001", "provider dropped"
    )

    statement = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert released is True
    assert "release_jarvis_agent_task" in statement
    assert params == {
        "task_id": "task-1",
        "agent_id": "mini-1",
        "attempt_id": "00000000-0000-0000-0000-000000000001",
        "reason": "provider dropped",
    }


def test_release_reports_a_refused_attempt_as_false():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = False
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine.begin = MagicMock(return_value=transaction)

    assert service.release("task-1", "mini-1", "00000000-0000-0000-0000-000000000001") is False


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


def _postgres_service_with_connection():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    service = AgentTaskQueueService(engine)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    transaction = MagicMock()
    transaction.__enter__.return_value = connection
    engine.begin = MagicMock(return_value=transaction)
    engine.connect = MagicMock(return_value=connection)
    return service, engine, connection


def test_enqueue_persists_creator_and_owner_and_scopes_idempotency():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = {
        "task_id": "task-owned",
        "owner_id": "owner-1",
        "created_by": "owner-1",
    }

    result = service.enqueue(
        "task-owned",
        "owned objective",
        idempotency_key="owner-scoped-key",
        created_by="owner-1",
        owner_id="owner-1",
    )

    statement = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert result["owner_id"] == "owner-1"
    assert "created_by" in statement
    assert "owner_id" in statement
    assert "IS NOT DISTINCT FROM excluded.owner_id" in statement
    assert params["created_by"] == "owner-1"
    assert params["owner_id"] == "owner-1"


def test_enqueue_rejects_idempotency_key_owned_by_another_user():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = None

    with pytest.raises(PermissionError, match="another owner"):
        service.enqueue(
            "task-owned-by-someone-else",
            "attempt to reuse another owner's idempotency key",
            idempotency_key="shared-key",
            created_by="owner-2",
            owner_id="owner-2",
        )


def test_create_routine_persists_owner_and_prevents_cross_owner_upsert():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = {
        "routine_key": "daily-check",
        "owner_id": "owner-1",
        "created_by": "owner-1",
    }

    result = service.create_routine(
        "daily-check",
        "Daily check",
        created_by="owner-1",
        owner_id="owner-1",
    )

    statement = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert result["owner_id"] == "owner-1"
    assert "created_by" in statement
    assert "owner_id" in statement
    assert "IS NOT DISTINCT FROM excluded.owner_id" in statement
    assert params["created_by"] == "owner-1"
    assert params["owner_id"] == "owner-1"


def test_create_routine_rejects_upsert_of_another_users_routine():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = None

    with pytest.raises(PermissionError, match="another owner"):
        service.create_routine(
            "daily-check",
            "Hijacked routine",
            created_by="owner-2",
            owner_id="owner-2",
        )


def test_trigger_routine_rejects_a_foreign_owner_before_materializing_task():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = {
        "routine_id": "00000000-0000-0000-0000-000000000001",
        "routine_key": "private-routine",
        "name": "Private routine",
        "priority": 50,
        "task_template": {"objective": "run private task"},
        "enabled": True,
        "created_by": "owner-1",
        "owner_id": "owner-1",
    }

    with pytest.raises(PermissionError, match="belongs to another owner"):
        service.trigger_routine("private-routine", "run-1", owner_id="owner-2")

    assert connection.execute.call_count == 1


def test_trigger_routine_copies_owner_and_creator_to_materialized_task():
    service, _, connection = _postgres_service_with_connection()
    routine = {
        "routine_id": "00000000-0000-0000-0000-000000000001",
        "routine_key": "private-routine",
        "name": "Private routine",
        "priority": 50,
        "task_template": {"objective": "run private task"},
        "enabled": True,
        "created_by": "owner-1",
        "owner_id": "owner-1",
    }
    select_result = MagicMock()
    select_result.mappings.return_value.first.return_value = routine
    insert_result = MagicMock()
    insert_result.mappings.return_value.first.return_value = {
        "task_id": "materialized-task",
        "owner_id": "owner-1",
        "created_by": "owner-1",
    }
    connection.execute.side_effect = [select_result, insert_result, MagicMock()]

    result = service.trigger_routine("private-routine", "run-1", owner_id="owner-1")

    insert_statement = str(connection.execute.call_args_list[1].args[0])
    insert_params = connection.execute.call_args_list[1].args[1]
    assert result["owner_id"] == "owner-1"
    assert "created_by" in insert_statement
    assert "owner_id" in insert_statement
    assert insert_params["created_by"] == "owner-1"
    assert insert_params["owner_id"] == "owner-1"


def test_triggering_global_routine_assigns_the_authenticated_caller_as_task_owner():
    service, _, connection = _postgres_service_with_connection()
    routine = {
        "routine_id": "00000000-0000-0000-0000-000000000001",
        "routine_key": "global-routine",
        "name": "Global routine",
        "priority": 50,
        "task_template": {"objective": "run global task"},
        "enabled": True,
        "created_by": None,
        "owner_id": None,
    }
    select_result = MagicMock()
    select_result.mappings.return_value.first.return_value = routine
    insert_result = MagicMock()
    insert_result.mappings.return_value.first.return_value = {
        "task_id": "materialized-task",
        "owner_id": "owner-2",
        "created_by": "owner-2",
    }
    connection.execute.side_effect = [select_result, insert_result, MagicMock()]

    service.trigger_routine("global-routine", "run-1", owner_id="owner-2")

    params = connection.execute.call_args_list[1].args[1]
    assert params["created_by"] == "owner-2"
    assert params["owner_id"] == "owner-2"


def test_get_task_owner_returns_persisted_owner():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = {
        "owner_id": "owner-42"
    }

    assert service.get_task_owner("task-42") == "owner-42"


def test_get_task_owner_returns_none_for_legacy_unowned_task():
    service, _, connection = _postgres_service_with_connection()
    connection.execute.return_value.mappings.return_value.first.return_value = {
        "owner_id": None
    }

    assert service.get_task_owner("legacy-task") is None
