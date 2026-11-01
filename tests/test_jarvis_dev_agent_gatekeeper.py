"""Security regressions for JarvisDevAgent's evolution gatekeeper dependency."""

from unittest.mock import MagicMock, patch

from app.application.services.jarvis_dev_agent import JarvisDevAgent


def test_code_proposal_is_rejected_when_gatekeeper_is_unavailable():
    agent = JarvisDevAgent()

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.return_value = None
        result = agent._run_gatekeeper("def candidate(): return True", "cap_test")

    assert result == {
        "approved": False,
        "reason": "gatekeeper_unavailable",
    }
    mock_nexus.resolve.assert_called_once_with("evolution_gatekeeper")


def test_code_proposal_uses_gatekeeper_decision_without_override():
    agent = JarvisDevAgent()
    gatekeeper = MagicMock()
    gatekeeper.approve_evolution.return_value = (False, "sandbox_unavailable")

    with patch("app.application.services.jarvis_dev_agent.agent.nexus") as mock_nexus:
        mock_nexus.resolve.return_value = gatekeeper
        result = agent._run_gatekeeper("def candidate(): return True", "cap_test")

    assert result == {
        "approved": False,
        "reason": "sandbox_unavailable",
    }
    gatekeeper.approve_evolution.assert_called_once_with(
        {
            "files_modified": [],
            "proposed_code": "def candidate(): return True",
            "cap_id": "cap_test",
        }
    )
