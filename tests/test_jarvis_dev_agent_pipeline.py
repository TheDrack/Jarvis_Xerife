"""JarvisDevAgent must delegate code evolution to the shared guarded pipeline."""
import threading
import time
from unittest.mock import MagicMock, patch

from app.application.services.jarvis_dev_agent import JarvisDevAgent


TARGET = "app/application/services/task_runner.py"


def _nexus_resolver(capabilities, orchestrator):
    capability_manager = MagicMock()
    capability_manager.get_executable_capabilities.return_value = capabilities

    def resolve(component_id):
        if component_id == "capability_manager":
            return capability_manager
        if component_id == "evolution_orchestrator":
            return orchestrator
        return None

    return capability_manager, resolve


def test_can_execute_requires_a_trusted_target_and_shared_orchestrator():
    capabilities = [
        {"id": "CAP-001", "title": "No target metadata"},
        {"id": "CAP-058", "title": "Adapt execution plans", "target_file": TARGET},
    ]
    orchestrator = MagicMock()
    capability_manager, resolver = _nexus_resolver(capabilities, orchestrator)
    agent = JarvisDevAgent()

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = resolver
        assert agent.can_execute() is True
        selected = agent._select_capability()

    assert selected["id"] == "CAP-058"
    assert selected["target_file"] == TARGET
    capability_manager.get_executable_capabilities.assert_called()


def test_can_execute_is_false_when_no_capability_has_a_trusted_target():
    capabilities = [{"id": "CAP-001", "title": "No target metadata"}]
    orchestrator = MagicMock()
    _, resolver = _nexus_resolver(capabilities, orchestrator)
    agent = JarvisDevAgent()

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = resolver
        assert agent.can_execute() is False

    orchestrator.execute.assert_not_called()


def test_context_target_cannot_replace_missing_capability_target():
    capabilities = [{"id": "CAP-001", "title": "No target metadata"}]
    orchestrator = MagicMock()
    _, resolver = _nexus_resolver(capabilities, orchestrator)
    agent = JarvisDevAgent()

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = resolver
        result = agent._execute_cycle(
            {"job_id": "job-1", "target_file": "app/application/services/task_runner.py"}
        )

    assert result["success"] is False
    assert result["reason"] == "no_executable_capability"
    orchestrator.execute.assert_not_called()


def test_execute_cycle_delegates_to_shared_orchestrator_with_trusted_context():
    capabilities = [
        {
            "id": "CAP-058",
            "title": "Adapt execution plans",
            "description": "Change a plan when execution conditions shift.",
            "target_file": TARGET,
        }
    ]
    orchestrator = MagicMock()
    orchestrator.execute.return_value = {
        "success": True,
        "validated": True,
        "dry_run": True,
        "target_file": TARGET,
        "source": "llm",
    }
    _, resolver = _nexus_resolver(capabilities, orchestrator)
    agent = JarvisDevAgent()
    agent.dry_run = True
    agent._get_few_shot_examples = MagicMock(
        return_value=[{"content": "A previous validated recovery strategy."}]
    )
    agent._get_consolidated_context = MagicMock(return_value="CODEBASE-CONTEXT")
    agent._record_cycle = MagicMock()

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.side_effect = resolver
        result = agent._execute_cycle(
            {"job_id": "job-058", "roadmap_context": "ROADMAP-CONTEXT"}
        )

    delegated = orchestrator.execute.call_args.args[0]
    assert delegated["cap_id"] == "CAP-058"
    assert delegated["mission_id"] == "job-058"
    assert delegated["target_file"] == TARGET
    assert delegated["dry_run"] is True
    assert "A previous validated recovery strategy." in delegated["roadmap_context"]
    assert "CODEBASE-CONTEXT" in delegated["roadmap_context"]
    assert "ROADMAP-CONTEXT" in delegated["roadmap_context"]
    assert result["success"] is True
    assert result["pr_created"] is False
    agent._record_cycle.assert_called_once()


def test_timeout_requests_cooperative_cancellation_without_waiting_for_worker():
    agent = JarvisDevAgent()
    started = threading.Event()
    observed = {}

    def slow_cycle(context):
        started.set()
        observed["event"] = context["_cancel_event"]
        context["_cancel_event"].wait(timeout=2)
        return {"success": False, "reason": "cancelled"}

    agent._execute_cycle = slow_cycle
    started_at = time.monotonic()
    result = agent._run_with_timeout({}, timeout_secs=0.5)
    elapsed = time.monotonic() - started_at

    assert result["reason"] == "timeout"
    assert result["cancellation_requested"] is True
    assert elapsed < 1.0
    assert started.is_set()
    assert observed["event"].is_set()
