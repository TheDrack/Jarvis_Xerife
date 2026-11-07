# -*- coding: utf-8 -*-
"""Tests for VectorMemoryAdapter - Happy Path validation"""

from datetime import datetime, timezone

import pytest

from app.adapters.infrastructure.vector_memory_adapter import (
    VectorMemoryAdapter,
    _vectorize,
)


class TestVectorize:
    """Unit tests for the internal _vectorize helper."""

    def test_returns_list_of_correct_length(self):
        vec = _vectorize("hello world", dim=64)
        assert len(vec) == 64

    def test_normalised_vector(self):
        import math

        vec = _vectorize("test normalisation", dim=64)
        magnitude = math.sqrt(sum(x * x for x in vec))
        assert abs(magnitude - 1.0) < 1e-6

    def test_empty_string_returns_zero_vector(self):
        vec = _vectorize("", dim=32)
        assert len(vec) == 32
        # All zeros when no tokens
        assert all(v == 0.0 for v in vec)


class TestVectorMemoryAdapter:
    """Integration-style tests for VectorMemoryAdapter (pure-Python path)."""

    @pytest.fixture
    def adapter(self):
        """Create adapter without FAISS (tests brute-force path)."""
        # Patch _FAISS_AVAILABLE to False so we test the pure-Python path
        import app.adapters.infrastructure.vector_memory_adapter as mod

        original = mod._FAISS_AVAILABLE
        mod._FAISS_AVAILABLE = False
        a = VectorMemoryAdapter(dim=64)
        a._index = None
        yield a
        mod._FAISS_AVAILABLE = original

    def test_store_event_returns_uuid(self, adapter):
        event_id = adapter.store_event("usuário pediu a hora")
        assert isinstance(event_id, str)
        assert len(event_id) == 36  # UUID format

    def test_store_and_query_similar_returns_match(self, adapter):
        adapter.store_event("o jarvis abriu o spotify")
        results = adapter.query_similar("abrir o spotify", top_k=1, days_back=None)
        assert len(results) == 1
        assert "text" in results[0]
        assert "score" in results[0]

    def test_query_similar_respects_top_k(self, adapter):
        for i in range(10):
            adapter.store_event(f"comando número {i}")
        results = adapter.query_similar("comando", top_k=3, days_back=None)
        assert len(results) <= 3

    def test_query_similar_with_days_back_filter(self, adapter):
        # Store one event well in the past (simulate by overriding timestamp)
        event_id = adapter.store_event("evento antigo")
        # Manually push its timestamp to 60 days ago
        for e in adapter._events:
            if e["id"] == event_id:
                old_ts = datetime(2000, 1, 1, tzinfo=timezone.utc)
                e["timestamp"] = old_ts.isoformat()
                break

        # Store a recent event
        adapter.store_event("evento recente")

        results = adapter.query_similar("evento", top_k=5, days_back=30)
        texts = [r["text"] for r in results]
        assert "evento recente" in texts
        assert "evento antigo" not in texts

    def test_clear_removes_all_events(self, adapter):
        adapter.store_event("algum texto")
        adapter.clear()
        assert adapter._events == []

    def test_execute_stores_event(self, adapter):
        result = adapter.execute({"text": "teste via execute"})
        assert result["success"] is True
        assert "event_id" in result
        assert len(adapter._events) == 1

    def test_execute_missing_text_returns_error(self, adapter):
        result = adapter.execute({})
        assert result["success"] is False

    def test_metadata_preserved(self, adapter):
        adapter.store_event("salvar metadata", metadata={"role": "user"})
        results = adapter.query_similar("salvar metadata", top_k=1, days_back=None)
        assert results[0]["metadata"] == {"role": "user"}


@pytest.fixture
def pii_vector_adapter():
    import app.adapters.infrastructure.vector_memory_adapter as mod

    original = mod._FAISS_AVAILABLE
    mod._FAISS_AVAILABLE = False
    adapter = VectorMemoryAdapter(dim=64)
    adapter._index = None
    yield adapter
    mod._FAISS_AVAILABLE = original


def test_store_event_uses_local_redactor_when_nexus_redactor_is_missing(
    monkeypatch, pii_vector_adapter
):
    from app.core.nexus import nexus

    monkeypatch.setattr(nexus, "resolve", lambda _name: None)

    pii_vector_adapter.store_event("Contact alice.smith@example.com, CPF 123.456.789-09")

    stored_text = pii_vector_adapter._events[0]["text"]
    assert "[EMAIL_REDACTED]" in stored_text
    assert "[CPF_REDACTED]" in stored_text
    assert "alice.smith@example.com" not in stored_text
    assert "123.456.789-09" not in stored_text


def test_store_event_refuses_an_invalid_registered_redactor(monkeypatch, pii_vector_adapter):
    from app.core.nexus import nexus

    monkeypatch.setattr(nexus, "resolve", lambda _name: object())

    with pytest.raises(RuntimeError, match="PII redactor is unavailable"):
        pii_vector_adapter.store_event("private email alice@example.com")

    assert pii_vector_adapter._events == []


def test_store_event_rejects_user_id_in_untrusted_metadata(
    monkeypatch, pii_vector_adapter
):
    from app.core.nexus import nexus

    monkeypatch.setattr(nexus, "resolve", lambda _name: None)

    with pytest.raises(ValueError, match="trusted argument"):
        pii_vector_adapter.store_event(
            "private event",
            metadata={"user_id": "alice"},
        )

    assert pii_vector_adapter._events == []

def test_store_event_rejects_conflicting_user_id_metadata(
    monkeypatch, pii_vector_adapter
):
    from app.core.nexus import nexus

    monkeypatch.setattr(nexus, "resolve", lambda _name: None)

    with pytest.raises(ValueError, match="conflicts with authenticated user_id"):
        pii_vector_adapter.store_event(
            "private event",
            metadata={"user_id": "bob"},
            user_id="alice",
        )

    assert pii_vector_adapter._events == []

class _SharedVectorMemoryStore:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.is_available = True

    def is_healthy(self):
        return True

    def append(self, event, user_id=None):
        self.events.append(dict(event))

    def list_events(self, user_id=None, days_back=None):
        return [
            dict(event)
            for event in self.events
            if event.get("metadata", {}).get("user_id") == user_id
        ]

    def delete_events(self, user_id=None):
        self.events[:] = [
            event
            for event in self.events
            if event.get("metadata", {}).get("user_id") != user_id
        ]

    def delete_all(self):
        self.events.clear()


def test_vector_memory_readback_survives_adapter_recreation():
    shared_events = []
    first = VectorMemoryAdapter(
        dim=32,
        store=_SharedVectorMemoryStore(shared_events),
    )
    first.store_event(
        "configure the Jarvis network connector",
        metadata={"kind": "fact"},
        user_id="alice",
    )

    restarted = VectorMemoryAdapter(
        dim=32,
        store=_SharedVectorMemoryStore(shared_events),
    )
    results = restarted.query_similar(
        "Jarvis network connector",
        top_k=1,
        user_id="alice",
        days_back=None,
    )

    assert len(results) == 1
    assert results[0]["metadata"]["user_id"] == "alice"


def test_vector_memory_store_partitions_users_and_system_scope():
    store = _SharedVectorMemoryStore()
    adapter = VectorMemoryAdapter(dim=32, store=store)
    adapter.store_event("alice private memory", user_id="alice")
    adapter.store_event("bob private memory", user_id="bob")
    adapter.store_event("system memory")

    alice = adapter.query_similar(
        "private memory", top_k=10, user_id="alice", days_back=None
    )
    system = adapter.query_similar(
        "system memory", top_k=10, user_id=None, days_back=None
    )

    assert [item["metadata"]["user_id"] for item in alice] == ["alice"]
    assert len(system) == 1
    assert "user_id" not in system[0]["metadata"]


def test_vector_memory_store_failure_does_not_cache_unpersisted_event():
    class FailingStore(_SharedVectorMemoryStore):
        def append(self, event, user_id=None):
            raise RuntimeError("database unavailable")

    adapter = VectorMemoryAdapter(dim=32, store=FailingStore())

    with pytest.raises(RuntimeError, match="database unavailable"):
        adapter.store_event("do not cache unpersisted event", user_id="alice")

    assert adapter._events == []


def test_vector_memory_durability_requires_a_configured_persistent_store():
    durable = VectorMemoryAdapter(dim=32, store=_SharedVectorMemoryStore())
    ephemeral = VectorMemoryAdapter(dim=32, store=None)

    assert durable.is_durable is True
    assert ephemeral.is_durable is False


def test_clear_only_removes_the_requested_user_partition():
    store = _SharedVectorMemoryStore()
    adapter = VectorMemoryAdapter(dim=32, store=store)
    adapter.store_event("alice memory", user_id="alice")
    adapter.store_event("bob memory", user_id="bob")

    adapter.clear(user_id="alice")

    assert len(store.list_events(user_id="alice")) == 0
    assert len(store.list_events(user_id="bob")) == 1

def test_vector_memory_clear_without_user_id_clears_all_partitions_explicitly():
    store = _SharedVectorMemoryStore()
    adapter = VectorMemoryAdapter(dim=32, store=store)
    adapter.store_event("alice memory", user_id="alice")
    adapter.store_event("system memory")

    adapter.clear()

    assert store.events == []
    assert adapter._events == []

def test_configured_but_unhealthy_vector_store_is_not_healthy():
    class UnhealthyStore(_SharedVectorMemoryStore):
        def is_healthy(self):
            return False

    adapter = VectorMemoryAdapter(dim=32, store=UnhealthyStore())

    assert adapter.is_durable is True
    assert adapter.is_healthy() is False
