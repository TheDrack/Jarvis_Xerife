from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.adapters.infrastructure.supabase_vector_memory_store import (
    SupabaseVectorMemoryStore,
)


def _client_with_query(data=None, *, raises=None):
    client = MagicMock()
    query = MagicMock()
    client.table.return_value = query
    query.select.return_value = query
    query.insert.return_value = query
    query.upsert.return_value = query
    query.delete.return_value = query
    query.eq.return_value = query
    query.gte.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.limit.return_value = query
    if raises is not None:
        query.execute.side_effect = raises
    else:
        query.execute.return_value = SimpleNamespace(data=data or [])
    return client, query


def test_append_uses_authoritative_scope_column_and_strips_user_from_metadata():
    client, query = _client_with_query()
    store = SupabaseVectorMemoryStore(client=client)
    event = {
        "id": "event-1",
        "text": "redacted event",
        "vector": [0.1, 0.2],
        "metadata": {"user_id": "alice", "kind": "fact"},
        "timestamp": datetime(2026, 11, 7, tzinfo=timezone.utc),
    }

    store.append(event)

    client.table.assert_called_once_with("jarvis_vector_memories")
    row = query.upsert.call_args.args[0]
    assert row["scope_key"] == "user:alice"
    assert row["user_id"] == "alice"
    assert row["metadata"] == {"kind": "fact"}
    assert row["event_text"] == "redacted event"
    assert row["embedding"] == [0.1, 0.2]
    assert row["vector_dim"] == 2
    assert query.upsert.call_args.kwargs == {"on_conflict": "id"}


def test_list_events_filters_by_user_scope_and_restores_trusted_user_id():
    row = {
        "id": "event-1",
        "scope_key": "user:alice",
        "user_id": "alice",
        "event_text": "redacted event",
        "embedding": [0.1, 0.2],
        "metadata": {"kind": "fact"},
        "created_at": "2026-11-07T00:00:00+00:00",
        "vector_dim": 2,
    }
    client, query = _client_with_query([row])
    store = SupabaseVectorMemoryStore(client=client)

    events = store.list_events(user_id="alice", days_back=None)

    query.eq.assert_called_once_with("scope_key", "user:alice")
    assert len(events) == 1
    assert events[0]["metadata"]["user_id"] == "alice"
    assert events[0]["vector"] == [0.1, 0.2]
    assert events[0]["text"] == "redacted event"


def test_list_events_keeps_system_scope_separate_from_user_partitions():
    client, query = _client_with_query([])
    store = SupabaseVectorMemoryStore(client=client)

    assert store.list_events(user_id=None, days_back=None) == []

    query.eq.assert_called_once_with("scope_key", "system")


def test_delete_events_only_deletes_the_requested_scope():
    client, query = _client_with_query()
    store = SupabaseVectorMemoryStore(client=client)

    store.delete_events(user_id="alice")

    query.eq.assert_called_once_with("scope_key", "user:alice")
    query.delete.assert_called_once_with()


def test_store_reports_unhealthy_when_supabase_query_fails():
    client, _ = _client_with_query(raises=RuntimeError("connection unavailable"))
    store = SupabaseVectorMemoryStore(client=client)

    assert store.is_healthy() is False


def test_store_without_service_client_is_not_available():
    store = SupabaseVectorMemoryStore(client=None)

    assert store.is_available is False
    assert store.is_healthy() is False

def test_append_rejects_user_identity_supplied_only_in_metadata():
    client, _ = _client_with_query()
    store = SupabaseVectorMemoryStore(client=client)
    event = {
        "id": "event-2",
        "text": "private event",
        "vector": [0.1, 0.2],
        "metadata": {"user_id": "alice"},
        "timestamp": datetime(2026, 11, 7, tzinfo=timezone.utc),
    }

    try:
        store.append(event)
    except ValueError as exc:
        assert "trusted user_id argument" in str(exc)
    else:
        raise AssertionError("untrusted metadata must not establish memory ownership")
