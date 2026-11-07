"""Tests for the fail-closed Cognitive Roadmap mission selector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.services.roadmap_mission_selector import (
    RoadmapManifestError,
    RoadmapMissionSelector,
)


ROADMAP_HEADING = "## 4. Fase 0 — Auditoria de capacidades e contratos"


def _repository(tmp_path: Path, missions=None) -> tuple[Path, dict]:
    (tmp_path / "docs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "app" / "services").mkdir(parents=True)
    (tmp_path / "app" / "application" / "services").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs" / "COGNITIVE_ROADMAP.md").write_text(
        "# Roadmap\n\n" + ROADMAP_HEADING + "\n\nC0 audit.\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "services" / "target.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_target.py").write_text(
        "def test_target():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "data" / "capabilities.json").write_text(
        json.dumps({"capabilities": [{"id": "CAP-058", "status": "pending"}]}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "roadmap_path": "docs/COGNITIVE_ROADMAP.md",
        "hold_reason": "No approved mission.",
        "missions": missions or [],
    }
    (tmp_path / "data" / "roadmap_missions.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return tmp_path, manifest


def _mission(**overrides):
    mission = {
        "criterion_id": "C0-BASELINE-PERCEPTION",
        "phase": "C0",
        "legacy_capability_id": "CAP-058",
        "status": "ready",
        "risk": "low",
        "priority": 1,
        "title": "Complete the C0 perception baseline",
        "objective": "Exercise the existing collector and core without creating a new event system.",
        "expected_result": "A deterministic regression test proves partial-source failure and event deduplication.",
        "roadmap_heading": ROADMAP_HEADING,
        "target_file": "app/services/target.py",
        "tests": ["tests/test_target.py"],
        "depends_on": [],
    }
    mission.update(overrides)
    return mission


def _selector(root: Path) -> RoadmapMissionSelector:
    return RoadmapMissionSelector(repository_root=root)


def test_empty_manifest_is_a_safe_noop_without_legacy_inventory_lookup(tmp_path):
    root, _ = _repository(tmp_path)
    (root / "data" / "capabilities.json").unlink()

    selector = _selector(root)

    assert selector.find_next_mission() is None
    assert selector.hold_reason == "No approved mission."


def test_selects_only_reviewed_low_risk_mission_and_builds_roadmap_context(tmp_path):
    root, _ = _repository(tmp_path, [_mission()])

    selected = _selector(root).find_next_mission()

    assert selected is not None
    assert selected["criterion_id"] == "C0-BASELINE-PERCEPTION"
    assert selected["legacy_capability_id"] == "CAP-058"
    assert selected["target_file"] == "app/services/target.py"
    assert selected["tests"] == ["tests/test_target.py"]
    assert '"source_of_truth": "docs/COGNITIVE_ROADMAP.md"' in selected["roadmap_context"]
    assert '"criterion_id": "C0-BASELINE-PERCEPTION"' in selected["roadmap_context"]


def test_priority_is_deterministic_and_dependencies_must_be_complete(tmp_path):
    dependency = _mission(
        criterion_id="C0-BASELINE-COLLECTOR",
        status="complete",
        priority=10,
    )
    blocked_by_dependency = _mission(
        criterion_id="C0-BASELINE-CORE",
        depends_on=["C0-BASELINE-COLLECTOR"],
        priority=1,
    )
    second_ready = _mission(
        criterion_id="C0-BASELINE-PROVENANCE",
        priority=2,
    )
    root, _ = _repository(
        tmp_path, [blocked_by_dependency, second_ready, dependency]
    )

    selected = _selector(root).find_next_mission()

    assert selected is not None
    assert selected["criterion_id"] == "C0-BASELINE-CORE"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"criterion_id": "CAP-058"}, "mission_criterion_id_invalid"),
        ({"phase": "C1"}, "mission_phase_mismatch"),
        ({"risk": "critical"}, "mission_risk_invalid"),
        ({"roadmap_heading": "## Nonexistent heading"}, "mission_roadmap_heading_not_found"),
        ({"target_file": "../outside.py"}, "mission_target_path_rejected"),
        ({"target_file": "app/application/security/policy.py"}, "mission_target_file_not_eligible"),
        ({"target_file": "app/application/services/roadmap_mission_selector.py"}, "mission_target_file_not_eligible"),
        ({"target_file": "scripts/evolve_all_pending.py"}, "mission_target_file_not_eligible"),
        ({"tests": []}, "mission_tests_required"),
        ({"tests": ["docs/COGNITIVE_ROADMAP.md"]}, "mission_test_path_invalid"),
        ({"legacy_capability_id": "CAP-999"}, "mission_legacy_capability_id_unknown"),
        ({"depends_on": ["C0-MISSING"]}, "roadmap_manifest_unknown_dependency"),
    ],
)
def test_rejects_invalid_or_untrusted_mission_metadata(tmp_path, overrides, message):
    root, _ = _repository(tmp_path, [_mission(**overrides)])
    if overrides.get("target_file") == "app/application/security/policy.py":
        protected = root / "app" / "application" / "security"
        protected.mkdir(parents=True)
        (protected / "policy.py").write_text("SAFE = True\n", encoding="utf-8")

    with pytest.raises(RoadmapManifestError, match=message):
        _selector(root).find_next_mission()


def test_ready_mission_with_medium_or_high_risk_is_not_selected(tmp_path):
    root, _ = _repository(
        tmp_path,
        [
            _mission(risk="medium"),
            _mission(
                criterion_id="C0-BASELINE-HIGH-RISK",
                risk="high",
                priority=2,
            ),
        ],
    )

    assert _selector(root).find_next_mission() is None


def test_mission_with_unfinished_dependency_is_not_selected(tmp_path):
    dependency = _mission(
        criterion_id="C0-BASELINE-DEPENDENCY",
        status="blocked",
        priority=1,
    )
    dependent = _mission(
        criterion_id="C0-BASELINE-DEPENDENT",
        depends_on=["C0-BASELINE-DEPENDENCY"],
        priority=2,
    )
    root, _ = _repository(tmp_path, [dependent, dependency])

    assert _selector(root).find_next_mission() is None


def test_manifest_with_unsupported_schema_fails_closed(tmp_path):
    root, manifest = _repository(tmp_path)
    manifest["schema_version"] = 2
    (root / "data" / "roadmap_missions.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(RoadmapManifestError, match="schema_version_unsupported"):
        _selector(root).find_next_mission()



def test_evolve_preserves_roadmap_criterion_in_candidate_artifact(monkeypatch):
    from scripts import evolve_all_pending

    class FakeOrchestrator:
        def __init__(self):
            self.context = None

        def execute(self, context):
            self.context = context
            return {"success": True}

    fake = FakeOrchestrator()
    monkeypatch.setattr(evolve_all_pending, "_get_orchestrator", lambda: fake)

    result = evolve_all_pending.evolve(
        "CAP-058",
        roadmap_context='{"criterion_id":"C0-BASELINE-PERCEPTION"}',
        target_file="app/services/target.py",
        mission_id="C0-BASELINE-PERCEPTION",
        mission_title="Complete the C0 perception baseline",
    )

    assert result is True
    assert fake.context["cap_id"] == "CAP-058"
    assert fake.context["mission_id"] == "C0-BASELINE-PERCEPTION"
    assert fake.context["cap_title"] == "Complete the C0 perception baseline"
    assert fake.context["target_file"] == "app/services/target.py"
