"""Tests for the read-only duplicate guard used before candidate generation."""

import io
import json
from unittest.mock import patch

import pytest

from scripts.roadmap_mission_guard import (
    RoadmapMissionGuardError,
    find_existing_mission_pr,
)


def _response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_finds_existing_open_or_merged_mission_pr():
    payload = [
        {
            "number": 321,
            "title": "[JARVIS Evolution] C0-001",
            "state": "closed",
            "merged_at": "2026-11-07T12:00:00Z",
            "html_url": "https://github.com/TheDrack/Jarvis_Xerife/pull/321",
        }
    ]
    with patch(
        "scripts.roadmap_mission_guard.urllib.request.urlopen",
        return_value=_response(payload),
    ) as open_url:
        result = find_existing_mission_pr(
            "TheDrack/Jarvis_Xerife", "C0-001", "read-only-token"
        )

    assert result["number"] == 321
    assert result["merged_at"] == "2026-11-07T12:00:00Z"
    request = open_url.call_args.args[0]
    assert "state=all" in request.full_url
    assert request.get_header("Authorization") == "Bearer read-only-token"


def test_returns_none_when_mission_has_no_prior_pr():
    with patch(
        "scripts.roadmap_mission_guard.urllib.request.urlopen",
        return_value=_response(
            [{"number": 320, "title": "[JARVIS Evolution] C0-002", "state": "open"}]
        ),
    ):
        assert (
            find_existing_mission_pr(
                "TheDrack/Jarvis_Xerife", "C0-001", "read-only-token"
            )
            is None
        )


def test_rejects_invalid_mission_id_before_network_access():
    with patch("scripts.roadmap_mission_guard.urllib.request.urlopen") as open_url:
        with pytest.raises(RoadmapMissionGuardError, match="mission_id_invalid"):
            find_existing_mission_pr(
                "TheDrack/Jarvis_Xerife", "CAP-058", "read-only-token"
            )
    open_url.assert_not_called()


def test_fails_closed_when_pull_request_lookup_is_unavailable():
    with patch(
        "scripts.roadmap_mission_guard.urllib.request.urlopen",
        side_effect=OSError("network unavailable"),
    ):
        with pytest.raises(
            RoadmapMissionGuardError, match="pull_request_lookup_failed"
        ):
            find_existing_mission_pr(
                "TheDrack/Jarvis_Xerife", "C0-001", "read-only-token"
            )
