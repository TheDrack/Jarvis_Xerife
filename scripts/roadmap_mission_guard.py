"""Read-only duplicate guard for roadmap-driven evolution publication."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

_MISSION_ID = re.compile(r"C[0-8]-[0-9]{3}\Z")
_MAX_PAGES = 20
_PAGE_SIZE = 100


class RoadmapMissionGuardError(RuntimeError):
    """The publisher cannot safely determine whether a mission PR already exists."""


def find_existing_mission_pr(
    repository: str,
    mission_id: str,
    token: str,
    *,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """Return an existing PR for this exact mission title, including closed/merged PRs.

    The API is read-only. Any authentication, HTTP, JSON, or pagination failure
    raises RoadmapMissionGuardError so the scheduled workflow can fail closed
    before invoking an LLM or sandbox.
    """
    if not isinstance(repository, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository
    ):
        raise RoadmapMissionGuardError("repository_identity_invalid")
    if not isinstance(mission_id, str) or not _MISSION_ID.fullmatch(mission_id):
        raise RoadmapMissionGuardError("mission_id_invalid")
    if not isinstance(token, str) or not token.strip():
        raise RoadmapMissionGuardError("github_read_token_missing")

    expected_title = f"[JARVIS Evolution] {mission_id}"
    for page in range(1, _MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{repository}/pulls"
            f"?state=all&per_page={_PAGE_SIZE}&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Jarvis-Roadmap-Mission-Guard",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RoadmapMissionGuardError(
                f"pull_request_lookup_failed:{type(exc).__name__}"
            ) from exc

        if not isinstance(payload, list):
            raise RoadmapMissionGuardError("pull_request_lookup_response_invalid")

        for item in payload:
            if isinstance(item, dict) and item.get("title") == expected_title:
                return {
                    "number": item.get("number"),
                    "state": item.get("state"),
                    "merged_at": item.get("merged_at"),
                    "html_url": item.get("html_url"),
                }

        if len(payload) < _PAGE_SIZE:
            return None

    raise RoadmapMissionGuardError("pull_request_lookup_pagination_limit_reached")
