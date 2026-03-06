# -*- coding: utf-8 -*-
"""Tests for CapabilityIndexService — MELHORIA 4."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.application.services.capability_index_service import CapabilityIndexService


_SAMPLE_CAPABILITIES = {
    "capabilities": [
        {
            "id": "CAP-001",
            "title": "Send email notification",
            "description": "Send email messages to users when events occur",
            "reliability_score": 1.0,
        },
        {
            "id": "CAP-002",
            "title": "Analyze system logs",
            "description": "Read and analyze system log files for errors",
            "reliability_score": 0.9,
        },
        {
            "id": "CAP-003",
            "title": "Execute Python code",
            "description": "Run Python scripts and return the output",
            "reliability_score": 0.8,
        },
    ]
}


@pytest.fixture
def caps_file(tmp_path):
    f = tmp_path / "capabilities.json"
    f.write_text(json.dumps(_SAMPLE_CAPABILITIES), encoding="utf-8")
    return f


@pytest.fixture
def service(caps_file):
    svc = CapabilityIndexService(top_k=3, direct_threshold=0.85)
    # Patch the capabilities file path
    import app.application.services.capability_index_service as mod
    original = mod._CAPABILITIES_FILE
    mod._CAPABILITIES_FILE = caps_file
    yield svc
    mod._CAPABILITIES_FILE = original


class TestCapabilityIndexServiceInit:
    def test_defaults(self):
        svc = CapabilityIndexService()
        assert svc._top_k == 3
        assert svc._direct_threshold == 0.85

    def test_configure(self):
        svc = CapabilityIndexService()
        svc.configure({"top_k": 5, "direct_threshold": 0.90})
        assert svc._top_k == 5
        assert svc._direct_threshold == 0.90


class TestCapabilityIndexServiceBuildAndFind:
    def test_build_index_returns_count(self, service):
        count = service._build_index()
        assert count == 3
        assert len(service._capabilities) == 3

    def test_find_capability_returns_results(self, service):
        results = service.find_capability("send email to user")
        assert len(results) > 0
        assert "id" in results[0]
        assert "similarity_score" in results[0]
        assert "reliability_score" in results[0]

    def test_find_capability_returns_at_most_top_k(self, service):
        results = service.find_capability("something")
        assert len(results) <= service._top_k

    def test_find_capability_empty_command(self, service):
        results = service.find_capability("")
        assert results == []

    def test_find_capability_triggers_build_if_not_loaded(self, service):
        assert not service._loaded
        service.find_capability("python code")
        assert service._loaded


class TestCapabilityIndexServiceReliabilityUpdate:
    def test_update_reliability_score_success(self, service, caps_file):
        service._build_index()
        result = service.update_reliability_score("CAP-001", success=True)
        assert result is True
        # Verify the file was updated
        data = json.loads(caps_file.read_text())
        cap = next(c for c in data["capabilities"] if c["id"] == "CAP-001")
        # new = 0.9*1.0 + 0.1*1.0 = 1.0 (stays at max)
        assert cap["reliability_score"] == pytest.approx(1.0, abs=1e-4)

    def test_update_reliability_score_failure(self, service, caps_file):
        service._build_index()
        result = service.update_reliability_score("CAP-001", success=False)
        assert result is True
        data = json.loads(caps_file.read_text())
        cap = next(c for c in data["capabilities"] if c["id"] == "CAP-001")
        # new = 0.9*1.0 + 0.1*0.0 = 0.9
        assert cap["reliability_score"] == pytest.approx(0.9, abs=1e-4)

    def test_update_nonexistent_capability_returns_false(self, service):
        service._build_index()
        result = service.update_reliability_score("CAP-NONEXISTENT", success=True)
        assert result is False


class TestCapabilityIndexServiceExecute:
    def test_execute_rebuild(self, service):
        result = service.execute({"action": "rebuild"})
        assert result["success"] is True
        assert result["action"] == "rebuild"
        assert result["indexed"] == 3

    def test_execute_find(self, service):
        result = service.execute({"action": "find", "command": "analyze logs"})
        assert result["success"] is True
        assert "results" in result
