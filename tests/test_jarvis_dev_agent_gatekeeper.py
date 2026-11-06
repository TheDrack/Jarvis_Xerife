"""JarvisDevAgent must not retain a parallel Gatekeeper execution path."""

from app.application.services.jarvis_dev_agent import JarvisDevAgent


def test_jarvis_dev_agent_has_no_private_gatekeeper_or_pr_pipeline():
    agent = JarvisDevAgent()

    assert not hasattr(agent, "_run_gatekeeper")
    assert not hasattr(agent, "_create_pr")
    assert not hasattr(agent, "_call_llm")
    assert not hasattr(agent, "_save_proposal")


def test_capability_selection_rejects_missing_or_blank_target_file(monkeypatch):
    agent = JarvisDevAgent()

    class CapabilityManager:
        def get_executable_capabilities(self):
            return [
                {"id": "missing-target"},
                {"id": "blank-target", "target_file": "  "},
            ]

    monkeypatch.setattr(
        "app.application.services.jarvis_dev_agent.agent.nexus.resolve",
        lambda name: CapabilityManager() if name == "capability_manager" else None,
    )

    assert agent._select_capability() is None
