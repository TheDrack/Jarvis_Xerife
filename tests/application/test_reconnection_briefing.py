from unittest.mock import patch

from app.application.services.reconnection_briefing import ReconnectionBriefing


def test_briefing_includes_verified_prs_updates_and_curiosity_cards():
    briefing = ReconnectionBriefing()
    curiosity = {
        "success": True,
        "records": [{
            "source_title": "Adaptive queue scheduling",
            "evidence_level": "documented",
            "status": "captured",
        }],
    }
    with patch("app.application.services.reconnection_briefing.nexus") as nexus:
        nexus.resolve.return_value.execute.return_value = curiosity
        result = briefing.execute({
            "verified_updates": [{"title": "Pause guard", "status": "tests pending"}],
            "pull_requests": [{
                "title": "PR #581",
                "status": "checks failing",
                "url": "https://github.com/TheDrack/Jarvis_Xerife/pull/581",
            }],
        })

    assert result["success"] is True
    assert "Pause guard: tests pending" in result["message"]
    assert "PR #581: checks failing" in result["message"]
    assert "Adaptive queue scheduling" in result["message"]
    assert "not proof of implementation" in result["claims_policy"]


def test_briefing_does_not_invent_updates_when_sources_are_empty():
    briefing = ReconnectionBriefing()
    with patch("app.application.services.reconnection_briefing.nexus") as nexus:
        nexus.resolve.return_value.execute.return_value = {"success": True, "records": []}
        result = briefing.execute({})

    assert result["success"] is True
    assert "Não encontrei novidades verificadas" in result["message"]
    assert result["pull_requests"] == []
    assert result["verified_updates"] == []


def test_briefing_ignores_malformed_pr_entries_and_limits_output():
    briefing = ReconnectionBriefing()
    with patch("app.application.services.reconnection_briefing.nexus") as nexus:
        nexus.resolve.return_value.execute.return_value = {"success": True, "records": []}
        result = briefing.execute({
            "limit": 1,
            "pull_requests": [None, {"title": "First PR", "status": "open"}, {"title": "Second PR", "status": "merged"}],
        })

    assert [item["title"] for item in result["pull_requests"]] == ["First PR"]
