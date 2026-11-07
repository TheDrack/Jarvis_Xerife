"""Regression tests for short-term to vector-memory consolidation."""

import app.adapters.infrastructure.vector_memory_adapter as vector_memory_module
from app.adapters.infrastructure.vector_memory_adapter import VectorMemoryAdapter
from app.application.services.memory_consolidation_service import (
    MemoryConsolidationService,
)
from app.domain.memory.working_memory import WorkingMemory


def test_consolidation_accepts_vector_adapter_without_faiss(monkeypatch):
    monkeypatch.setattr(vector_memory_module, "_FAISS_AVAILABLE", False)
    vector_adapter = VectorMemoryAdapter(dim=32)
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
