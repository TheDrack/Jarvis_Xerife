"""Regression tests for short-term to vector-memory consolidation."""

import app.adapters.infrastructure.vector_memory_adapter as vector_memory_module
from app.adapters.infrastructure.vector_memory_adapter import VectorMemoryAdapter
from app.application.services.memory_consolidation_service import (
    MemoryConsolidationService,
)
from app.domain.memory.working_memory import WorkingMemory


def test_consolidation_accepts_vector_adapter_without_faiss(monkeypatch):
    monkeypatch.setattr(vector_memory_module, "_FAISS_AVAILABLE", False)
    vector_adapter = VectorMemoryAdapter(dim=32, store=_DurableStore())
    assert vector_adapter.is_healthy() is True
    working_memory = WorkingMemory()
    working_memory.push(
        {
            "user_input": "configure router authentication",
            "response": "Use authenticated service endpoints.",
            "_ts": "2000-01-01T00:00:00+00:00",
        }
    )
    service = MemoryConsolidationService(
        working_memory=working_memory,
        vector_adapter=vector_adapter,
    )

    consolidated = service.consolidate_memories(max_age_hours=24)

    assert consolidated == 1
    assert working_memory.size == 0
    results = vector_adapter.query_similar(
        "router authentication",
        top_k=1,
        days_back=None,
    )
    assert len(results) == 1
    assert "authenticated service endpoints" in results[0]["text"]

class _DurableStore:
    is_available = True

    def __init__(self):
        self.events = []

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


def test_consolidation_preserves_working_memory_without_durable_vector_store():
    working_memory = WorkingMemory()
    working_memory.push(
        {
            "user_input": "keep this until durable storage is available",
            "response": "Do not evict this item.",
            "_ts": "2000-01-01T00:00:00+00:00",
        }
    )
    service = MemoryConsolidationService(
        working_memory=working_memory,
        vector_adapter=VectorMemoryAdapter(dim=32, store=None),
    )

    consolidated = service.consolidate_memories(max_age_hours=24)

    assert consolidated == 0
    assert working_memory.size == 1
