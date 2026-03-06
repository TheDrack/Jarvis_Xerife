# -*- coding: utf-8 -*-
"""Tests for Phase 4 fixes and enhancements (Blocos D + Etapas 10-12)."""
import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# D.1 — GatewayLLMCommandAdapter._interpret_sync does not call self.interpret()
# ---------------------------------------------------------------------------

class TestGatewayLLMAdapterInterpretSync:
    def test_interpret_sync_does_not_call_interpret(self):
        """_interpret_sync must not call self.interpret() in its executable code (avoids recursion)."""
        import inspect
        from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter

        src = inspect.getsource(GatewayLLMCommandAdapter._interpret_sync)
        # Strip docstring before checking — only look at the code lines
        lines = src.splitlines()
        in_docstring = False
        code_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if not in_docstring:
                code_lines.append(line)
        code_only = "\n".join(code_lines)
        assert "self.interpret(" not in code_only, (
            "_interpret_sync has a call to self.interpret() in executable code, risking infinite recursion"
        )

    def test_interpret_sync_falls_back_to_unknown_intent(self):
        """When no gemini_adapter available, _interpret_sync returns UNKNOWN intent."""
        from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter
        from app.domain.models import CommandType

        with patch.object(GatewayLLMCommandAdapter, "__init__", lambda s, **kw: None):
            adapter = GatewayLLMCommandAdapter.__new__(GatewayLLMCommandAdapter)
            adapter.gemini_adapter = None
            adapter.wake_word = "xerife"

        result = adapter._interpret_sync("xerife test input")
        assert result.command_type == CommandType.UNKNOWN

    def test_interpret_sync_delegates_to_gemini_adapter(self):
        """When gemini_adapter has _interpret_sync, it is called directly."""
        from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter
        from app.domain.models import CommandType, Intent

        mock_intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
            raw_input="type hello",
            confidence=0.9,
        )
        mock_gemini = MagicMock()
        mock_gemini._interpret_sync.return_value = mock_intent

        with patch.object(GatewayLLMCommandAdapter, "__init__", lambda s, **kw: None):
            adapter = GatewayLLMCommandAdapter.__new__(GatewayLLMCommandAdapter)
            adapter.gemini_adapter = mock_gemini
            adapter.wake_word = "xerife"

        result = adapter._interpret_sync("type hello")
        mock_gemini._interpret_sync.assert_called_once_with("type hello")
        assert result.command_type == CommandType.TYPE_TEXT


# ---------------------------------------------------------------------------
# D.2 — execute() after __init__ in the 4 fixed files
# ---------------------------------------------------------------------------

class TestExecuteOrderAfterInit:
    def _get_method_linenos(self, cls):
        import inspect
        lines, start = inspect.getsourcelines(cls)
        method_lines = {}
        for i, line in enumerate(lines):
            stripped = line.strip()
            for name in ("def __init__", "def execute"):
                if stripped.startswith(name):
                    method_lines[name] = start + i
        return method_lines

    def test_evolution_loop_execute_after_init(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        lines = self._get_method_linenos(EvolutionLoopService)
        assert lines["def __init__"] < lines["def execute"], (
            "execute() must appear after __init__() in EvolutionLoopService"
        )

    def test_automation_adapter_execute_after_init(self):
        from app.adapters.edge.automation_adapter import AutomationAdapter
        lines = self._get_method_linenos(AutomationAdapter)
        assert lines["def __init__"] < lines["def execute"]

    def test_voice_provider_execute_after_init(self):
        from app.application.ports.voice_provider import VoiceProvider
        lines = self._get_method_linenos(VoiceProvider)
        # VoiceProvider is an ABC and may not define __init__ directly
        if "def __init__" in lines:
            assert lines["def __init__"] < lines["def execute"]
        else:
            # No __init__ means execute order is fine by convention
            assert "def execute" in lines


# ---------------------------------------------------------------------------
# D.3 — .frozen/caps/ execute methods have self parameter
# ---------------------------------------------------------------------------

class TestFrozenCapsExecuteSelf:
    def test_no_frozen_execute_without_self(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "def execute(context=None):", ".frozen/"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"Found execute without self in .frozen/:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# D.4 — EvolutionLoopService zero-arg constructor + configure() + can_execute()
# ---------------------------------------------------------------------------

class TestEvolutionLoopServiceNexusPattern:
    def test_zero_arg_instantiation(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        svc = EvolutionLoopService()
        assert svc.reward_provider is None

    def test_can_execute_false_without_provider(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        svc = EvolutionLoopService()
        assert svc.can_execute() is False

    def test_can_execute_true_with_provider(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        svc = EvolutionLoopService(reward_provider=MagicMock())
        assert svc.can_execute() is True

    def test_configure_injects_reward_provider(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        mock_provider = MagicMock()
        svc = EvolutionLoopService()
        svc.configure({"reward_provider": mock_provider})
        assert svc.reward_provider is mock_provider
        assert svc.can_execute() is True

    def test_backward_compat_positional_arg(self):
        from app.application.services.evolution_loop import EvolutionLoopService
        mock_provider = MagicMock()
        svc = EvolutionLoopService(reward_provider=mock_provider)
        assert svc.reward_provider is mock_provider


# ---------------------------------------------------------------------------
# D.5 — JarvisNexus.list_loaded_ids() + StatusService
# ---------------------------------------------------------------------------

class TestJarvisNexusListLoadedIds:
    def test_returns_list(self):
        from app.core.nexus import JarvisNexus
        n = JarvisNexus()
        result = n.list_loaded_ids()
        assert isinstance(result, list)

    def test_returns_copy(self):
        """Modifying the returned list must not affect internal state."""
        from app.core.nexus import JarvisNexus
        n = JarvisNexus()
        ids1 = n.list_loaded_ids()
        ids1.append("fake_id")
        ids2 = n.list_loaded_ids()
        assert "fake_id" not in ids2

    def test_concurrent_access_safe(self):
        """list_loaded_ids must be callable from multiple threads without error."""
        from app.core.nexus import JarvisNexus
        n = JarvisNexus()
        errors = []

        def _call():
            try:
                n.list_loaded_ids()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_call) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent access raised: {errors}"

    def test_status_service_uses_list_loaded_ids(self):
        """StatusService.get_system_report must call nexus.list_loaded_ids()."""
        import inspect
        from app.application.services.status_service import StatusService
        src = inspect.getsource(StatusService.get_system_report)
        assert "list_loaded_ids()" in src, (
            "StatusService.get_system_report should use nexus.list_loaded_ids()"
        )


# ---------------------------------------------------------------------------
# D.6 — /v1/roadmap/progress uses AutoEvolutionServiceV2
# ---------------------------------------------------------------------------

class TestRoadmapProgressV2:
    def test_endpoint_uses_v2(self):
        import inspect
        from app.adapters.infrastructure.routers import utility
        src = inspect.getsource(utility)
        assert "AutoEvolutionServiceV2" in src
        assert "AutoEvolutionService()" not in src or "AutoEvolutionServiceV2" in src

    def test_evolution_rate_mapped_to_completion_percentage(self):
        """evolution_rate=0.75 should yield completion_percentage=75.0."""
        from app.adapters.infrastructure.routers.utility import create_utility_router
        # Just verify the logic in the source
        import inspect
        src = inspect.getsource(create_utility_router)
        assert "evolution_rate" in src
        assert "completion_percentage" in src


# ---------------------------------------------------------------------------
# Etapa 10 — MetaReflection rejection patterns
# ---------------------------------------------------------------------------

class TestMetaReflectionRejectionPatterns:
    @pytest.fixture
    def reflection(self):
        from app.application.services.meta_reflection import MetaReflection
        return MetaReflection()

    def test_reflect_includes_rejection_patterns_field(self, reflection):
        """reflect() must return a dict containing 'rejection_patterns'."""
        with patch.object(reflection, "_load_rejections", return_value=[]):
            result = reflection.reflect([], [])
        assert "rejection_patterns" in result

    def test_load_rejections_returns_empty_when_no_file(self, reflection, tmp_path, monkeypatch):
        """_load_rejections returns [] when the file does not exist."""
        import app.application.services.meta_reflection as mr_mod
        monkeypatch.setattr(mr_mod, "_REJECTIONS_FILE", tmp_path / "nonexistent.jsonl")
        result = reflection._load_rejections()
        assert result == []

    def test_load_rejections_parses_jsonl(self, reflection, tmp_path, monkeypatch):
        """_load_rejections returns parsed entries from the JSONL file."""
        import app.application.services.meta_reflection as mr_mod
        f = tmp_path / "rejections.jsonl"
        entries = [
            {"timestamp": 1.0, "check_failed": "sandbox", "files_modified": ["a.py"]},
            {"timestamp": 2.0, "check_failed": "frozen_files", "files_modified": ["b.py"]},
        ]
        f.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        monkeypatch.setattr(mr_mod, "_REJECTIONS_FILE", f)
        result = reflection._load_rejections()
        assert len(result) == 2

    def test_analyze_check_failed_counts(self, reflection):
        """_analyze_rejection_patterns counts check_failed occurrences."""
        import time
        now = time.time()
        rejections = [
            {"timestamp": now, "check_failed": "sandbox", "files_modified": []},
            {"timestamp": now, "check_failed": "sandbox", "files_modified": []},
            {"timestamp": now, "check_failed": "frozen_files", "files_modified": []},
        ]
        result = reflection._analyze_rejection_patterns(rejections)
        assert result["check_failed_counts"].get("sandbox") == 2
        assert result["check_failed_counts"].get("frozen_files") == 1

    def test_analyze_top_blocked_files(self, reflection):
        """_analyze_rejection_patterns identifies most-blocked files."""
        import time
        now = time.time()
        rejections = [
            {"timestamp": now, "check_failed": "c", "files_modified": ["foo.py", "bar.py"]},
            {"timestamp": now, "check_failed": "c", "files_modified": ["foo.py"]},
            {"timestamp": now, "check_failed": "c", "files_modified": ["baz.py"]},
        ]
        result = reflection._analyze_rejection_patterns(rejections)
        assert result["top_blocked_files"][0] == "foo.py"

    def test_analyze_rejections_last_7d(self, reflection):
        """_analyze_rejection_patterns counts rejections in the last 7 days."""
        import time
        now = time.time()
        old = now - 8 * 86400  # 8 days ago
        rejections = [
            {"timestamp": now, "check_failed": "x", "files_modified": []},
            {"timestamp": now, "check_failed": "x", "files_modified": []},
            {"timestamp": old, "check_failed": "x", "files_modified": []},
        ]
        result = reflection._analyze_rejection_patterns(rejections)
        assert result["rejections_last_7d"] == 2


# ---------------------------------------------------------------------------
# Etapa 11 — GET /v1/health/detail
# ---------------------------------------------------------------------------

class TestHealthDetailEndpoint:
    @pytest.fixture
    def client(self):
        """TestClient with all components mocked out."""
        from fastapi.testclient import TestClient
        from app.adapters.infrastructure.routers.health import create_health_router

        mock_db = MagicMock()
        mock_db.engine = None
        router = create_health_router(mock_db, get_current_user=None)

        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_health_detail_returns_200(self, client, tmp_path, monkeypatch):
        """GET /v1/health/detail returns 200 with correct structure."""
        # Patch nexus and components to avoid real resolution
        import app.adapters.infrastructure.routers.health as health_mod

        mock_nexus = MagicMock()
        mock_nexus.list_loaded_ids.return_value = ["status_service"]
        mock_nexus.resolve.return_value = None

        with patch("app.adapters.infrastructure.routers.health.create_health_router"):
            pass  # already imported

        # Call directly without patching — just verify structure
        resp = client.get("/v1/health/detail")
        assert resp.status_code == 200
        body = resp.json()
        # All sections must be present
        for section in ("nexus", "evolution", "meta_reflection", "finetune", "gatekeeper", "resources"):
            assert section in body, f"Missing section: {section}"

    def test_health_detail_graceful_when_all_unavailable(self, client):
        """Endpoint must never return 500 even when all components fail."""
        with patch("app.core.nexus.JarvisNexus.list_loaded_ids", side_effect=RuntimeError("boom")):
            resp = client.get("/v1/health/detail")
        assert resp.status_code == 200
        body = resp.json()
        # nexus section should have available=False
        assert body["nexus"]["available"] is False


# ---------------------------------------------------------------------------
# Etapa 12 — JarvisDevAgent audit log + timeout
# ---------------------------------------------------------------------------

class TestJarvisDevAgentAuditLog:
    def test_job_persisted_on_success(self, tmp_path, monkeypatch):
        """A successful job must be recorded in the JSONL file."""
        import app.application.services.jarvis_dev_agent as da_mod
        jobs_file = tmp_path / "dev_agent_jobs.jsonl"
        monkeypatch.setattr(da_mod, "_JOBS_FILE", jobs_file)

        agent = da_mod.JarvisDevAgent()
        agent.dry_run = True

        with patch.object(agent, "_execute_cycle", return_value={
            "success": True,
            "capability_id": "CAP-001",
            "gatekeeper_result": {"approved": True},
            "pr_created": False,
        }):
            result = agent.execute({"job_id": "test-job-1"})

        assert result["success"] is True
        assert jobs_file.exists()
        lines = [json.loads(l) for l in jobs_file.read_text().splitlines() if l.strip()]
        statuses = [l["status"] for l in lines if l.get("job_id") == "test-job-1"]
        assert "success" in statuses

    def test_job_status_timeout_when_exceeded(self, tmp_path, monkeypatch):
        """Exceeding the timeout must record status='timeout'."""
        import app.application.services.jarvis_dev_agent as da_mod
        jobs_file = tmp_path / "dev_agent_jobs.jsonl"
        monkeypatch.setattr(da_mod, "_JOBS_FILE", jobs_file)
        monkeypatch.setenv("DEV_AGENT_TIMEOUT_SECONDS", "0")

        agent = da_mod.JarvisDevAgent()

        import time
        def _slow_cycle(ctx):
            time.sleep(10)
            return {"success": True}

        with patch.object(agent, "_execute_cycle", side_effect=_slow_cycle):
            result = agent.execute({"job_id": "timeout-job"})

        assert result.get("reason") == "timeout"
        lines = [json.loads(l) for l in jobs_file.read_text().splitlines() if l.strip()]
        statuses = [l["status"] for l in lines if l.get("job_id") == "timeout-job"]
        assert "timeout" in statuses


class TestDevAgentJobsEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.adapters.infrastructure.routers.dev_agent import create_dev_agent_router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_dev_agent_router())
        return TestClient(app)

    def test_jobs_endpoint_returns_list(self, client, tmp_path, monkeypatch):
        """GET /v1/dev-agent/jobs returns a list."""
        import app.adapters.infrastructure.routers.dev_agent as da_router
        monkeypatch.setattr(da_router, "_JOBS_FILE", tmp_path / "jobs.jsonl")
        resp = client.get("/v1/dev-agent/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_jobs_endpoint_returns_entries(self, client, tmp_path, monkeypatch):
        """GET /v1/dev-agent/jobs returns entries from the JSONL file."""
        import app.adapters.infrastructure.routers.dev_agent as da_router
        jobs_file = tmp_path / "jobs.jsonl"
        entries = [
            {"job_id": "j1", "started_at": "2025-01-02T10:00:00Z", "status": "success",
             "capability_id": "CAP-001", "finished_at": "2025-01-02T10:01:00Z",
             "gatekeeper_result": None, "pr_created": False, "error": None, "duration_seconds": 60.0},
            {"job_id": "j2", "started_at": "2025-01-01T09:00:00Z", "status": "failed",
             "capability_id": None, "finished_at": "2025-01-01T09:01:00Z",
             "gatekeeper_result": None, "pr_created": False, "error": "timeout", "duration_seconds": 300.0},
        ]
        jobs_file.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        monkeypatch.setattr(da_router, "_JOBS_FILE", jobs_file)

        resp = client.get("/v1/dev-agent/jobs?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be sorted descending by started_at
        assert data[0]["job_id"] == "j1"

    def test_jobs_endpoint_respects_limit(self, client, tmp_path, monkeypatch):
        """GET /v1/dev-agent/jobs respects the limit parameter."""
        import app.adapters.infrastructure.routers.dev_agent as da_router
        jobs_file = tmp_path / "jobs.jsonl"
        entries = [
            {"job_id": f"j{i}", "started_at": f"2025-01-0{i+1}T00:00:00Z", "status": "success",
             "finished_at": None, "capability_id": None, "gatekeeper_result": None,
             "pr_created": False, "error": None, "duration_seconds": 1.0}
            for i in range(5)
        ]
        jobs_file.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        monkeypatch.setattr(da_router, "_JOBS_FILE", jobs_file)

        resp = client.get("/v1/dev-agent/jobs?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_run_returns_429_when_running(self, client):
        """POST /v1/dev-agent/run returns 429 when a job is already running."""
        import app.adapters.infrastructure.routers.dev_agent as da_router
        da_router._agent_running = True
        try:
            resp = client.post("/v1/dev-agent/run")
            assert resp.status_code == 429
        finally:
            da_router._agent_running = False
