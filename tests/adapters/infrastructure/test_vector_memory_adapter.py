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
