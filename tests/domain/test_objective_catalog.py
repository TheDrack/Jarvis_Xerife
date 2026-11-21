# -*- coding: utf-8 -*-
"""ADR-006 R1: roadmap objectives live in the ``objective:`` namespace.

``data/capabilities.json`` used to mix roadmap objectives with executable
capabilities: bare ``CAP-###`` identifiers and 68 heuristic ``complete``
entries with no execution evidence. These tests pin the migrated contract so
the two namespaces cannot be compared by accident and a completion claim
without evidence fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.services.capability_binding_registry import (
    NamespaceViolation,
    normalize_capability_id,
)
from app.application.services.roadmap_mission_selector import RoadmapMissionSelector
from app.domain.capabilities.objectives import (
    OBJECTIVE_STATUSES,
    ObjectiveCatalogError,
    is_objective_id,
    normalize_objective_id,
    validate_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _real_catalog() -> dict:
    path = REPO_ROOT / "data" / "capabilities.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(**overrides):
    entry = {
        "id": "objective:CAP-001",
        "title": "A",
        "description": "B",
        "status": "pending",
        "auto": True,
        "priority": 1,
        "depends_on": [],
        "notes": "fixture",
    }
    entry.update(overrides)
    return entry


def _catalog(*entries):
    return {"capabilities": list(entries)}


def test_real_catalog_uses_the_objective_namespace_end_to_end():
    payload = _real_catalog()
    validated = validate_catalog(payload)

    assert len(validated) == 102
    assert all(is_objective_id(item["id"]) for item in validated)
    assert all(
        dependency.startswith("objective:")
        for item in validated
        for dependency in item["depends_on"]
    )
    assert all(item["status"] in OBJECTIVE_STATUSES for item in validated)
    raw_ids = [entry["id"] for entry in payload["capabilities"]]
    assert len(set(raw_ids)) == len(raw_ids)


def test_real_catalog_has_no_completion_claim_without_execution_evidence():
    entries = _real_catalog()["capabilities"]
    statuses: dict[str, int] = {}
    for entry in entries:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1

    assert statuses.get("complete", 0) == 0
    assert statuses.get("unverified", 0) == 68
    assert all("evidence" not in entry for entry in entries)
    unverified = [entry for entry in entries if entry["status"] == "unverified"]
    assert all(entry.get("claimed_status") == "complete" for entry in unverified)


def test_real_catalog_does_not_share_identifiers_with_the_execution_catalog():
    registry_path = REPO_ROOT / "config" / "tool_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    tool_capabilities = {
        capability
        for tool in registry["tools"]
        for capability in tool.get("capabilities", [])
    }
    objective_ids = {entry["id"] for entry in _real_catalog()["capabilities"]}

    assert objective_ids.isdisjoint(tool_capabilities)
    assert not any(value.startswith("objective:") for value in tool_capabilities)


def test_roadmap_selector_reads_the_migrated_objective_catalog():
    identifiers = RoadmapMissionSelector()._load_capability_ids()

    assert len(identifiers) == 102
    assert all(is_objective_id(value) for value in identifiers)
    assert "objective:CAP-058" in identifiers


def test_complete_objective_requires_passing_execution_evidence():
    with pytest.raises(
        ObjectiveCatalogError, match="requires an execution evidence object"
    ):
        validate_catalog(_catalog(_entry(status="complete")))

    with pytest.raises(ObjectiveCatalogError, match="missing a non-empty 'recorded_at'"):
        validate_catalog(
            _catalog(
                _entry(
                    status="complete",
                    evidence={"command": "pytest -q", "result": "passed"},
                )
            )
        )

    with pytest.raises(ObjectiveCatalogError, match="must record result 'passed'"):
        validate_catalog(
            _catalog(
                _entry(
                    status="complete",
                    evidence={
                        "command": "pytest -q",
                        "result": "failed",
                        "recorded_at": "2026-11-21",
                    },
                )
            )
        )


def test_complete_objective_with_full_evidence_is_accepted():
    validated = validate_catalog(
        _catalog(
            _entry(
                status="complete",
                evidence={
                    "command": "pytest tests/domain -q",
                    "result": "passed",
                    "recorded_at": "2026-11-21",
                },
            )
        )
    )

    assert validated[0]["status"] == "complete"
    assert validated[0]["evidence"]["command"] == "pytest tests/domain -q"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_catalog(_entry(id="CAP-001")), "must use the 'objective:' namespace"),
        (
            _catalog(_entry(id="capability:screen.capture")),
            "must use the 'objective:' namespace",
        ),
        (_catalog(_entry(), _entry()), "duplicate objective id"),
        (
            _catalog(_entry(depends_on=["objective:CAP-999"])),
            "depends on unknown objective",
        ),
        (_catalog(_entry(depends_on=["objective:CAP-001"])), "depends on itself"),
        (
            _catalog(_entry(depends_on=["CAP-002"])),
            "must list objective:CAP-### identifiers",
        ),
        (_catalog(_entry(status="done")), "invalid objective status"),
        (
            _catalog(_entry(status="unverified", claimed_status="unverified")),
            "must differ from status",
        ),
    ],
)
def test_catalog_rejects_invalid_objectives(payload, message):
    with pytest.raises(ObjectiveCatalogError, match=message):
        validate_catalog(payload)


def test_capability_namespace_refuses_objectives_and_vice_versa():
    with pytest.raises(NamespaceViolation):
        normalize_capability_id("objective:CAP-001")
    with pytest.raises(
        ObjectiveCatalogError, match="capability identifiers are executable"
    ):
        normalize_objective_id("capability:screen.capture")


def test_normalize_objective_id_accepts_the_legacy_form():
    assert normalize_objective_id("CAP-042") == "objective:CAP-042"
    assert normalize_objective_id(" objective:CAP-042 ") == "objective:CAP-042"
    with pytest.raises(ObjectiveCatalogError):
        normalize_objective_id("CAP-42")
