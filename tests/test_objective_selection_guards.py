"""Regression tests for objective eligibility and evidence-backed completion."""

import json
import sys

import pytest
from sqlmodel import create_engine

from app.application.services.auto_evolutionV2 import AutoEvolutionServiceV2
from app.application.services.capability_manager import CapabilityManager
from app.domain.capabilities.objectives import ObjectiveCatalogError, validate_catalog
from scripts import evolve_all_pending


def _objectives():
    return [
        {
            "id": "objective:CAP-001",
            "title": "Completed prerequisite",
            "status": "complete",
            "depends_on": [],
            "evidence": {
                "command": "pytest -q",
                "result": "passed",
                "recorded_at": "2026-11-22T10:00:00Z",
            },
        },
        {
            "id": "objective:CAP-002",
            "title": "Blocked despite completed dependencies",
            "status": "blocked",
            "depends_on": ["objective:CAP-001"],
            "priority": 1,
        },
        {
            "id": "objective:CAP-003",
            "title": "Pending objective",
            "status": "pending",
            "depends_on": [],
            "priority": 5,
        },
        {
            "id": "objective:CAP-004",
            "title": "Unverified historical claim",
            "status": "unverified",
            "claimed_status": "complete",
            "depends_on": ["objective:CAP-001"],
            "priority": 10,
        },
    ]


def _write_catalog(path, objectives):
    path.write_text(
        json.dumps({"capabilities": objectives}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_auto_evolution_service_never_selects_blocked_objectives(tmp_path):
    path = tmp_path / "capabilities.json"
    _write_catalog(path, _objectives())

    service = AutoEvolutionServiceV2(str(path))
    selected = service.find_next_mission()

    assert selected is not None
    assert selected["id"] == "objective:CAP-003"


def test_capability_manager_excludes_blocked_but_keeps_legacy_statuses():
    manager = CapabilityManager(engine=create_engine("sqlite:///:memory:"))
    manager._load_capabilities_json = lambda: [
        {"id": "objective:CAP-001", "status": "complete", "depends_on": []},
        {
            "id": "objective:CAP-002",
            "status": "blocked",
            "depends_on": ["objective:CAP-001"],
        },
        {"id": "objective:CAP-003", "status": "pending", "depends_on": []},
        {"id": "legacy:CAP-004", "status": "nonexistent", "depends_on": []},
    ]

    selected = manager.get_executable_capabilities()
    selected_ids = {item["id"] for item in selected}

    assert selected_ids == {"objective:CAP-003", "legacy:CAP-004"}


def test_batch_selection_excludes_blocked_objectives():
    selected = evolve_all_pending._topological_sort(
        _objectives(), {"objective:CAP-001"}
    )

    selected_ids = [item["id"] for item in selected]
    assert selected_ids == ["objective:CAP-003", "objective:CAP-004"]
    assert "objective:CAP-002" not in selected_ids


def test_explicit_batch_selection_rejects_blocked_objective(monkeypatch):
    monkeypatch.setattr(evolve_all_pending, "_load_capabilities", _objectives)
    monkeypatch.setattr(
        sys, "argv", ["evolve_all_pending.py", "--cap-id", "objective:CAP-002"]
    )

    with pytest.raises(SystemExit) as raised:
        evolve_all_pending.main()

    assert raised.value.code == 1


def test_mark_mission_as_completed_requires_and_persists_execution_evidence(tmp_path):
    path = tmp_path / "capabilities.json"
    original = [
        {
            "id": "objective:CAP-001",
            "title": "Historical heuristic completion",
            "status": "unverified",
            "claimed_status": "complete",
            "depends_on": [],
        }
    ]
    _write_catalog(path, original)
    service = AutoEvolutionServiceV2(str(path))

    with pytest.raises(TypeError):
        service.mark_mission_as_completed("CAP-001")

    with pytest.raises(ObjectiveCatalogError):
        service.mark_mission_as_completed(
            "CAP-001",
            evidence={
                "command": "pytest -q",
                "result": "failed",
                "recorded_at": "2026-11-22T10:00:00Z",
            },
        )

    assert json.loads(path.read_text(encoding="utf-8"))["capabilities"][0]["status"] == "unverified"

    assert service.mark_mission_as_completed(
        "CAP-001",
        evidence={
            "command": "pytest tests/domain -q",
            "result": "passed",
            "recorded_at": "2026-11-22T10:05:00Z",
        },
    ) is True

    updated = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_catalog(updated)
    assert validated[0]["status"] == "complete"
    assert validated[0]["evidence"]["result"] == "passed"
    assert "claimed_status" not in updated["capabilities"][0]
